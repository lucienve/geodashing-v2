output "bucket_name" {
  description = "The name of the GCS bucket storing user media assets."
  value       = google_storage_bucket.blobs.name
}

output "bucket_url" {
  description = "The storage URL of the media bucket."
  value       = google_storage_bucket.blobs.url
}

output "service_account_email" {
  description = "The email address of the uploader service account."
  value       = google_service_account.geodashing_uploader.email
}

output "backend_processing_key_id" {
  description = "The resource ID of the Gemini Backend Processing API key."
  value       = google_apikeys_key.backend_processing.id
}

output "backend_api_key_id" {
  description = "The resource ID of the Backend Maps API key."
  value       = google_apikeys_key.backend_api_key.id
}

output "ui_api_key_id" {
  description = "The resource ID of the UI Maps API key."
  value       = google_apikeys_key.ui_api_key.id
}
