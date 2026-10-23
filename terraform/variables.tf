variable "project_id" {
  description = "The GCP project ID to manage resources in."
  type        = string
  default     = "geodashing-v2"
}

variable "project_number" {
  description = "The numeric GCP project number."
  type        = string
  default     = "927002408097"
}

variable "region" {
  description = "The default GCP region for regional resources."
  type        = string
  default     = "us-east1"
}
