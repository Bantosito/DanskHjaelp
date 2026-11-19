variable "environments" {
  description = "Environments that get their own database on the shared server."
  type        = set(string)
  default     = ["dev", "prod"]
}

variable "postgres_sku" {
  description = "Postgres compute size. B_Standard_B1ms is the smallest."
  type        = string
  default     = "B_Standard_B1ms"
}
