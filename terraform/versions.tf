terraform {
  required_version = ">= 1.7.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # Remote state storage in dedicated GCS bucket with versioning enabled.
  backend "gcs" {
    bucket = "geodashing-v2-tfstate"
    prefix = "terraform/state"
  }
}
