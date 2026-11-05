terraform {
  required_version = ">= 1.11"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "azurerm" {
  features {}

  # Resource providers are registered once by hand (see infra/README.md), because the
  # pipeline identities are deliberately not allowed to do it at subscription level.
  resource_provider_registrations = "none"
  storage_use_azuread             = true
}
