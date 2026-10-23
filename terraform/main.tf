# -----------------------------------------------------------------------------
# Google Cloud Storage - Media Assets Bucket
# -----------------------------------------------------------------------------

resource "google_storage_bucket" "blobs" {
  name                        = "geodashing-v2-blobs"
  location                    = "US-EAST1"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = false

  autoclass {
    enabled                = true
    terminal_storage_class = "ARCHIVE"
  }

  soft_delete_policy {
    retention_duration_seconds = 604800
  }

  lifecycle {
    prevent_destroy = true
  }
}

# -----------------------------------------------------------------------------
# Cloud Storage Bucket IAM Bindings (Non-authoritative)
# -----------------------------------------------------------------------------

# Public read access for dashpoint visit photos and thumbnails
resource "google_storage_bucket_iam_member" "blobs_public_viewer" {
  bucket = google_storage_bucket.blobs.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# Full object administration for backend uploader service account
resource "google_storage_bucket_iam_member" "uploader_admin" {
  bucket = google_storage_bucket.blobs.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.geodashing_uploader.email}"
}

# -----------------------------------------------------------------------------
# Service Accounts & Project IAM Bindings
# -----------------------------------------------------------------------------

resource "google_service_account" "geodashing_uploader" {
  account_id   = "geodashing-uploader"
  display_name = "Geodashing Service Account"
  description  = "Geodashing Email and GCS storage access"
}

# Vertex AI / Gemini user role for server-side AI summary generation
resource "google_project_iam_member" "uploader_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.geodashing_uploader.email}"
}

# -----------------------------------------------------------------------------
# Google Cloud API Keys
# -----------------------------------------------------------------------------

# API Key for Gemini / Generative Language API
resource "google_apikeys_key" "backend_processing" {
  name         = "a7f2aab3-6a7b-448b-92b0-c14afcf65fe4"
  display_name = "Backend processing"
  project      = var.project_id

  restrictions {
    api_targets {
      service = "generativelanguage.googleapis.com"
    }
  }
}

# API Key for Backend Maps Services (Geocoding, Timezone, Elevation) restricted to host IP
resource "google_apikeys_key" "backend_api_key" {
  name         = "02c51582-f7d5-4b90-ade8-bfb3a1eb652c"
  display_name = "Backend API Key"
  project      = var.project_id

  restrictions {
    api_targets {
      service = "geocoding-backend.googleapis.com"
    }

    api_targets {
      service = "timezone-backend.googleapis.com"
    }

    api_targets {
      service = "elevation-backend.googleapis.com"
    }

    server_key_restrictions {
      allowed_ips = ["35.211.240.85"]
    }
  }
}

# API Key for Client-Side Maps UI restricted to authorized web referrers
resource "google_apikeys_key" "ui_api_key" {
  name         = "5b387efe-d0ea-4246-b7cf-09193bff1dea"
  display_name = "UI API Key"
  project      = var.project_id

  restrictions {
    api_targets {
      service = "maps-backend.googleapis.com"
    }

    browser_key_restrictions {
      allowed_referrers = [
        "*geodashing.org/*",
        "*127.0.0.1/*",
        "*localhost/*",
      ]
    }
  }
}
