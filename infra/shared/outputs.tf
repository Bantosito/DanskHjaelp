output "container_app_environment_id" {
  value = azurerm_container_app_environment.main.id
}

output "registry_id" {
  value = azurerm_container_registry.main.id
}

output "registry_name" {
  value = azurerm_container_registry.main.name
}

output "registry_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "postgres_fqdn" {
  value = azurerm_postgresql_flexible_server.main.fqdn
}

output "postgres_admin_login" {
  value = azurerm_postgresql_flexible_server.main.administrator_login
}

output "postgres_admin_password" {
  value     = random_password.postgres_admin.result
  sensitive = true
}
