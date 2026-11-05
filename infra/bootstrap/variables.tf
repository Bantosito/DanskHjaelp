variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "swedencentral"
}

variable "github_subject_prefix" {
  description = "The only repository allowed to sign in to Azure. GitHub names it by immutable IDs, so re-creating the name elsewhere can't match."
  type        = string
  default     = "repo:Bantosito@72502994/DanskHjaelp@1446988561"
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
