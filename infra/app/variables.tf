variable "environment" {
  description = "Which environment this is."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "Environment must be dev or prod."
  }
}

variable "image" {
  description = "Full image reference to run. Passed by the pipeline."
  type        = string
}

variable "min_replicas" {
  description = "0 scales to zero when idle: cheapest, but the first message after idle is slower."
  type        = number
  default     = 0
}

variable "state_storage_account" {
  description = "Where the shared stack's state lives."
  type        = string
  default     = "stdanskhjaelp04191c"
}
