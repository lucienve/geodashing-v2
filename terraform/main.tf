# -----------------------------------------------------------------------------
# Google Cloud Project Services (APIs)
# -----------------------------------------------------------------------------

resource "google_project_service" "compute" {
  project            = var.project_id
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "batch" {
  project            = var.project_id
  service            = "batch.googleapis.com"
  disable_on_destroy = false

  depends_on = [
    google_project_service.compute,
  ]
}

resource "google_project_service" "logging" {
  project            = var.project_id
  service            = "logging.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "monitoring" {
  project            = var.project_id
  service            = "monitoring.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "storage" {
  project            = var.project_id
  service            = "storage.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifactregistry" {
  project            = var.project_id
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "containerfilesystem" {
  project            = var.project_id
  service            = "containerfilesystem.googleapis.com"
  disable_on_destroy = false

  depends_on = [
    google_project_service.artifactregistry,
  ]
}

# -----------------------------------------------------------------------------
# Google Cloud Storage - Media Assets Bucket
# -----------------------------------------------------------------------------

resource "google_storage_bucket" "blobs" {
  name                        = "geodashing-v2-blobs"
  location                    = "US-EAST1"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = false

  hierarchical_namespace {
    enabled = true
  }

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
# Google Cloud Storage - Road & Map Datasets Bucket
# -----------------------------------------------------------------------------

resource "google_storage_bucket" "map_data" {
  name                        = "geodashing-v2-map-data"
  location                    = "US-EAST1"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  autoclass {
    enabled                = true
    terminal_storage_class = "ARCHIVE"
  }

  versioning {
    enabled = true
  }

  soft_delete_policy {
    retention_duration_seconds = 604800
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      days_since_noncurrent_time = 180
      with_state                 = "ARCHIVED"
    }
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      num_newer_versions = 2
      with_state         = "ARCHIVED"
    }
  }

  lifecycle_rule {
    action {
      type = "AbortIncompleteMultipartUpload"
    }
    condition {
      age = 7
    }
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age            = 7
      matches_prefix = ["cache/"]
      with_state     = "LIVE"
    }
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      days_since_noncurrent_time = 1
      matches_prefix             = ["cache/"]
      with_state                 = "ARCHIVED"
    }
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

# Full object administration on road/map data bucket for backend service account
resource "google_storage_bucket_iam_member" "map_data_uploader_admin" {
  bucket = google_storage_bucket.map_data.name
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

# Cloud Batch agent reporter role for road dataset preparation
resource "google_project_iam_member" "uploader_batch_reporter" {
  project = var.project_id
  role    = "roles/batch.agentReporter"
  member  = "serviceAccount:${google_service_account.geodashing_uploader.email}"
}

# Cloud Logging writer role for road dataset preparation
resource "google_project_iam_member" "uploader_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.geodashing_uploader.email}"
}

# Cloud Monitoring metric writer role for Cloud Batch VM telemetry
resource "google_project_iam_member" "uploader_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.geodashing_uploader.email}"
}

# -----------------------------------------------------------------------------
# Google Artifact Registry - Cloud Batch Container Images
# -----------------------------------------------------------------------------

resource "google_artifact_registry_repository" "batch" {
  location      = var.region
  repository_id = "batch"
  description   = "Container images for Geodashing Cloud Batch jobs"
  format        = "DOCKER"

  cleanup_policies {
    id     = "keep-recent-versions"
    action = "KEEP"

    most_recent_versions {
      keep_count = 3
    }
  }

  cleanup_policies {
    id     = "delete-old-versions"
    action = "DELETE"

    condition {
      tag_state  = "ANY"
      older_than = "604800s"
    }
  }

  depends_on = [
    google_project_service.artifactregistry,
  ]
}

# Reader access on the batch repository for the batch VM service account
resource "google_artifact_registry_repository_iam_member" "uploader_batch_reader" {
  project    = var.project_id
  location   = google_artifact_registry_repository.batch.location
  repository = google_artifact_registry_repository.batch.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.geodashing_uploader.email}"
}

# -----------------------------------------------------------------------------
# Google Cloud API Keys
# -----------------------------------------------------------------------------

# API Key for Gemini / Generative Language API
resource "google_apikeys_key" "backend_processing" {
  name         = "a7f2aab3-6a7b-448b-92b0-c14afcf65fe4"
  display_name = "Backend processing"
  project      = var.project_number

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
  project      = var.project_number

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
  project      = var.project_number

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
