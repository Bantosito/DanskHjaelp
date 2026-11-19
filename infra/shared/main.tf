data "azurerm_resource_group" "shared" {
  name = "rg-danskhjaelp-shared"
}

locals {
  resource_group_name = data.azurerm_resource_group.shared.name
  location            = data.azurerm_resource_group.shared.location
}

# Registry and Postgres names are global across Azure, so they need a unique suffix.
resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

# Network. The database has no public address and is only reachable from inside this VNet.
resource "azurerm_virtual_network" "main" {
  name                = "vnet-danskhjaelp"
  resource_group_name = local.resource_group_name
  location            = local.location
  address_space       = ["10.20.0.0/16"]
}

resource "azurerm_subnet" "apps" {
  name                 = "snet-apps"
  resource_group_name  = local.resource_group_name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.20.0.0/23"]

  delegation {
    name = "container-apps"

    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "postgres" {
  name                 = "snet-postgres"
  resource_group_name  = local.resource_group_name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.20.2.0/28"]

  delegation {
    name = "postgres"

    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_private_dns_zone" "postgres" {
  name                = "danskhjaelp.private.postgres.database.azure.com"
  resource_group_name = local.resource_group_name
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  name                  = "postgres"
  resource_group_name   = local.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.postgres.name
  virtual_network_id    = azurerm_virtual_network.main.id
}

# Database
resource "random_password" "postgres_admin" {
  length  = 32
  special = false
}

resource "azurerm_postgresql_flexible_server" "main" {
  name                          = "psql-danskhjaelp-${random_string.suffix.result}"
  resource_group_name           = local.resource_group_name
  location                      = local.location
  version                       = "16"
  sku_name                      = var.postgres_sku
  storage_mb                    = 32768
  backup_retention_days         = 7
  delegated_subnet_id           = azurerm_subnet.postgres.id
  private_dns_zone_id           = azurerm_private_dns_zone.postgres.id
  public_network_access_enabled = false
  administrator_login           = "dhadmin"
  administrator_password        = random_password.postgres_admin.result

  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]

  lifecycle {
    # Holds the learning history. Terraform refuses any plan that would delete it.
    prevent_destroy = true
    ignore_changes  = [zone]
  }
}

resource "azurerm_postgresql_flexible_server_configuration" "extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "VECTOR"
}

resource "azurerm_postgresql_flexible_server_database" "environment" {
  for_each = var.environments

  name      = "danskhjaelp_${each.key}"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"

  lifecycle {
    prevent_destroy = true
  }
}

# Images
resource "azurerm_container_registry" "main" {
  name                = "crdanskhjaelp${random_string.suffix.result}"
  resource_group_name = local.resource_group_name
  location            = local.location
  sku                 = "Basic"
  admin_enabled       = false
}

# Logs, capped so a logging loop can't run up a bill.
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-danskhjaelp"
  resource_group_name = local.resource_group_name
  location            = local.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 0.5
}

# Where the apps and jobs run. A consumption-only environment has no base fee.
resource "azurerm_container_app_environment" "main" {
  name                       = "cae-danskhjaelp"
  resource_group_name        = local.resource_group_name
  location                   = local.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  infrastructure_subnet_id   = azurerm_subnet.apps.id

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }
}
