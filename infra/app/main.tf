data "terraform_remote_state" "shared" {
  backend = "azurerm"

  config = {
    resource_group_name  = "rg-danskhjaelp-state"
    storage_account_name = var.state_storage_account
    container_name       = "tfstate"
    key                  = "shared.tfstate"
    use_azuread_auth     = true
  }
}

data "azurerm_client_config" "current" {}

data "azurerm_resource_group" "environment" {
  name = "rg-danskhjaelp-${var.environment}"
}

locals {
  shared              = data.terraform_remote_state.shared.outputs
  resource_group_name = data.azurerm_resource_group.environment.name
  location            = data.azurerm_resource_group.environment.location

  database_name = "danskhjaelp_${var.environment}"
  app_db_role   = "dh_${var.environment}"
  database_host = "${local.shared.postgres_fqdn}:5432/${local.database_name}?sslmode=require"

  # Names of the Key Vault secrets the containers read, and the variable each one becomes.
  app_secrets = {
    telegram-bot-token       = "TELEGRAM_BOT_TOKEN"
    telegram-allowed-user-id = "TELEGRAM_ALLOWED_USER_ID"
    telegram-webhook-secret  = "TELEGRAM_WEBHOOK_SECRET"
    database-url             = "DATABASE_URL"
  }
  release_secrets = merge(local.app_secrets, {
    database-admin-url = "DATABASE_ADMIN_URL"
    app-db-password    = "APP_DB_PASSWORD"
  })
  secret_ids = merge(
    { for name, secret in azurerm_key_vault_secret.manual : name => secret.versionless_id },
    { for name, secret in azurerm_key_vault_secret.generated : name => secret.versionless_id },
  )
}

# The identity the containers run as: it can read this vault and pull images, nothing else.
resource "azurerm_user_assigned_identity" "app" {
  name                = "id-danskhjaelp-${var.environment}"
  resource_group_name = local.resource_group_name
  location            = local.location
}

resource "random_string" "vault_suffix" {
  length  = 6
  upper   = false
  special = false
}

resource "azurerm_key_vault" "main" {
  name                       = "kv-dh-${var.environment}-${random_string.vault_suffix.result}"
  resource_group_name        = local.resource_group_name
  location                   = local.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
}

resource "azurerm_role_assignment" "app_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_role_assignment" "app_images" {
  scope                = local.shared.registry_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# New role assignments take a moment to apply across Azure.
resource "time_sleep" "role_propagation" {
  create_duration = "60s"

  depends_on = [azurerm_role_assignment.app_secrets, azurerm_role_assignment.app_images]
}

# Set by hand after creation. Write-only values stay out of Terraform state, and with a fixed
# version Terraform never overwrites what was set.
resource "azurerm_key_vault_secret" "manual" {
  for_each = {
    telegram-bot-token       = "0:placeholder"
    telegram-allowed-user-id = "0"
  }

  name             = each.key
  key_vault_id     = azurerm_key_vault.main.id
  value_wo         = each.value
  value_wo_version = 1
}

resource "random_password" "webhook_secret" {
  length  = 48
  special = false
}

resource "random_password" "app_db" {
  length  = 32
  special = false
}

resource "azurerm_key_vault_secret" "generated" {
  for_each = {
    telegram-webhook-secret = random_password.webhook_secret.result
    app-db-password         = random_password.app_db.result
    database-url            = "postgresql+psycopg://${local.app_db_role}:${random_password.app_db.result}@${local.database_host}"
    database-admin-url      = "postgresql+psycopg://${local.shared.postgres_admin_login}:${local.shared.postgres_admin_password}@${local.database_host}"
  }

  name         = each.key
  key_vault_id = azurerm_key_vault.main.id
  value        = each.value
}

resource "azurerm_container_app" "bot" {
  name                         = "ca-danskhjaelp-${var.environment}"
  resource_group_name          = local.resource_group_name
  container_app_environment_id = local.shared.container_app_environment_id
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = local.shared.registry_login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  dynamic "secret" {
    for_each = local.app_secrets

    content {
      name                = secret.key
      key_vault_secret_id = local.secret_ids[secret.key]
      identity            = azurerm_user_assigned_identity.app.id
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.min_replicas
    max_replicas = 1

    http_scale_rule {
      name                = "http"
      concurrent_requests = "10"
    }

    container {
      name   = "bot"
      image  = var.image
      cpu    = 0.25
      memory = "0.5Gi"

      dynamic "env" {
        for_each = local.app_secrets

        content {
          name        = env.value
          secret_name = env.key
        }
      }

      liveness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/healthz"
      }
    }
  }

  depends_on = [time_sleep.role_propagation]
}

# Runs inside the VNet on every deploy, because the database can't be reached from outside it.
resource "azurerm_container_app_job" "release" {
  name                         = "caj-dh-${var.environment}-release"
  resource_group_name          = local.resource_group_name
  location                     = local.location
  container_app_environment_id = local.shared.container_app_environment_id
  workload_profile_name        = "Consumption"
  replica_timeout_in_seconds   = 300
  replica_retry_limit          = 0

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = local.shared.registry_login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  dynamic "secret" {
    for_each = local.release_secrets

    content {
      name                = secret.key
      key_vault_secret_id = local.secret_ids[secret.key]
      identity            = azurerm_user_assigned_identity.app.id
    }
  }

  template {
    container {
      name    = "release"
      image   = var.image
      cpu     = 0.25
      memory  = "0.5Gi"
      command = ["python", "-m", "danskhjaelp.release"]

      dynamic "env" {
        for_each = local.release_secrets

        content {
          name        = env.value
          secret_name = env.key
        }
      }

      env {
        name  = "APP_DB_ROLE"
        value = local.app_db_role
      }

      env {
        name  = "PUBLIC_URL"
        value = "https://${azurerm_container_app.bot.ingress[0].fqdn}"
      }
    }
  }

  depends_on = [time_sleep.role_propagation]
}
