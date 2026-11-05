output "state_resource_group" {
  value = azurerm_resource_group.state.name
}

output "state_storage_account" {
  value = azurerm_storage_account.state.name
}

output "state_container" {
  value = azurerm_storage_container.state.name
}

output "tenant_id" {
  value = data.azurerm_client_config.current.tenant_id
}

output "subscription_id" {
  value = data.azurerm_client_config.current.subscription_id
}

output "plan_client_id" {
  value = azurerm_user_assigned_identity.plan.client_id
}

output "deploy_client_ids" {
  value = { for environment, identity in azurerm_user_assigned_identity.deploy : environment => identity.client_id }
}
