variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "swedencentral"
}

variable "github_repository" {
  description = "The only repository allowed to sign in to Azure, as owner/name."
  type        = string
  default     = "Bantosito/DanskHjaelp"
}

variable "budget_email" {
  description = "Where budget alerts go. Passed at apply time so it stays out of this public repo."
  type        = string
  sensitive   = true
}

variable "budget_start_date" {
  description = "First day of the first budget month. Azure requires the first of a month."
  type        = string
  default     = "2026-11-01T00:00:00Z"
}
