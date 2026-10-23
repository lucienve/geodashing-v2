terraform {
  required_version = ">= 1.7.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # Remote backend configuration template. Uncomment and configure after provisioning
  # a dedicated GCS state bucket (e.g., geodashing-v2-tfstate) with versioning enabled.
  # backend "gcs" {
  #   bucket = "geodashing-v2-tfstate"
  #   prefix = "terraform/state"
  # }
}
