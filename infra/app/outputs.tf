output "url" {
  value = "https://${azurerm_container_app.bot.ingress[0].fqdn}"
}

output "resource_group" {
  value = local.resource_group_name
}

output "app_name" {
  value = azurerm_container_app.bot.name
}

output "release_job_name" {
  value = azurerm_container_app_job.release.name
}

output "key_vault_name" {
  value = azurerm_key_vault.main.name
}
