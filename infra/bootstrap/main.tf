data "azurerm_client_config" "current" {}
data "azurerm_subscription" "current" {}

locals {
  environments = toset(["dev", "prod"])
  stacks       = toset(["shared", "dev", "prod"])
}

resource "azurerm_resource_group" "state" {
  name     = "rg-danskhjaelp-state"
  location = var.location
}

resource "azurerm_resource_group" "stack" {
  for_each = local.stacks

  name     = "rg-danskhjaelp-${each.key}"
  location = var.location
}

# Terraform state. It holds generated passwords, so access keys are turned off and only
# identities with an explicit role can read it. Versioning allows recovery from a bad write.
resource "random_string" "state_suffix" {
  length  = 6
  upper   = false
  special = false
}

resource "azurerm_storage_account" "state" {
  name                            = "stdanskhjaelp${random_string.state_suffix.result}"
  resource_group_name             = azurerm_resource_group.state.name
  location                        = azurerm_resource_group.state.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  shared_access_key_enabled       = false
  default_to_oauth_authentication = true
  allow_nested_items_to_be_public = false

  blob_properties {
    versioning_enabled = true

    delete_retention_policy {
      days = 30
    }
  }
}

resource "azurerm_storage_container" "state" {
  name                  = "tfstate"
  storage_account_id    = azurerm_storage_account.state.id
  container_access_type = "private"
}

resource "azurerm_role_assignment" "state_operator" {
  scope                = azurerm_storage_container.state.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

# Identities GitHub Actions signs in as. Federated credentials trust short-lived tokens that
# GitHub issues for this repository, so no Azure password is stored anywhere.
resource "azurerm_user_assigned_identity" "plan" {
  name                = "id-danskhjaelp-plan"
  resource_group_name = azurerm_resource_group.state.name
  location            = azurerm_resource_group.state.location
}

resource "azurerm_federated_identity_credential" "plan" {
  name      = "github-pull-request"
  parent_id = azurerm_user_assigned_identity.plan.id
  issuer    = "https://token.actions.githubusercontent.com"
  audience  = ["api://AzureADTokenExchange"]
  subject   = "${var.github_subject_prefix}:pull_request"
}

resource "azurerm_user_assigned_identity" "deploy" {
  for_each = local.environments

  name                = "id-danskhjaelp-deploy-${each.key}"
  resource_group_name = azurerm_resource_group.state.name
  location            = azurerm_resource_group.state.location
}

resource "azurerm_federated_identity_credential" "deploy" {
  for_each = local.environments

  name      = "github-environment-${each.key}"
  parent_id = azurerm_user_assigned_identity.deploy[each.key].id
  issuer    = "https://token.actions.githubusercontent.com"
  audience  = ["api://AzureADTokenExchange"]
  subject   = "${var.github_subject_prefix}:environment:${each.key}"
}

# The plan identity reads everything Terraform has to refresh and changes nothing. Plain Reader
# isn't enough, because the azurerm provider also lists app secrets and workspace keys.
resource "azurerm_role_definition" "plan" {
  name  = "DanskHjaelp Terraform Plan"
  scope = data.azurerm_subscription.current.id

  permissions {
    actions = [
      "*/read",
      "Microsoft.App/containerApps/listSecrets/action",
      "Microsoft.App/jobs/listSecrets/action",
      "Microsoft.OperationalInsights/workspaces/sharedKeys/action",
    ]
  }

  assignable_scopes = [data.azurerm_subscription.current.id]
}

resource "azurerm_role_assignment" "plan_read" {
  for_each = local.stacks

  scope              = azurerm_resource_group.stack[each.key].id
  role_definition_id = azurerm_role_definition.plan.role_definition_resource_id
  principal_id       = azurerm_user_assigned_identity.plan.principal_id
}

resource "azurerm_role_assignment" "plan_secrets" {
  for_each = local.environments

  scope                = azurerm_resource_group.stack[each.key].id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.plan.principal_id
}

resource "azurerm_role_assignment" "plan_state" {
  scope                = azurerm_storage_container.state.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.plan.principal_id
}

# Each deploy identity manages its own environment and the shared stack it depends on.
locals {
  deploy_assignments = merge([
    for environment in local.environments : merge(
      {
        for role in ["Contributor", "Role Based Access Control Administrator", "Key Vault Secrets Officer"] :
        "${environment}/${environment}/${role}" => {
          environment = environment
          scope       = azurerm_resource_group.stack[environment].id
          role        = role
        }
      },
      {
        for role in ["Contributor", "Role Based Access Control Administrator"] :
        "${environment}/shared/${role}" => {
          environment = environment
          scope       = azurerm_resource_group.stack["shared"].id
          role        = role
        }
      },
      {
        "${environment}/state" = {
          environment = environment
          scope       = azurerm_storage_container.state.id
          role        = "Storage Blob Data Contributor"
        }
      },
    )
  ]...)
}

resource "azurerm_role_assignment" "deploy" {
  for_each = local.deploy_assignments

  scope                = each.value.scope
  role_definition_name = each.value.role
  principal_id         = azurerm_user_assigned_identity.deploy[each.value.environment].principal_id
}

# Images are built once and promoted, so only the first stage needs to push them.
resource "azurerm_role_assignment" "dev_image_push" {
  scope                = azurerm_resource_group.stack["shared"].id
  role_definition_name = "AcrPush"
  principal_id         = azurerm_user_assigned_identity.deploy["dev"].principal_id
}

resource "azurerm_consumption_budget_subscription" "monthly" {
  name            = "budget-danskhjaelp"
  subscription_id = data.azurerm_subscription.current.id
  amount          = 30
  time_grain      = "Monthly"

  time_period {
    start_date = var.budget_start_date
  }

  # Alerts at about $10, $20 and $30 of actual spend. Azure only takes whole percentages.
  dynamic "notification" {
    for_each = [33, 67, 100]

    content {
      enabled        = true
      threshold      = notification.value
      threshold_type = "Actual"
      operator       = "GreaterThanOrEqualTo"
      contact_emails = [var.budget_email]
    }
  }
}
