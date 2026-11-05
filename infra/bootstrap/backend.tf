terraform {
  backend "azurerm" {
    key = "bootstrap.tfstate"
  }
}
