# -----------------------------------------------------------------------------
# Declarative Resource Imports (Terraform 1.5+)
# Adopts existing Google Cloud resources without destroying or recreating them.
# -----------------------------------------------------------------------------

import {
  to = google_storage_bucket.blobs
  id = "geodashing-v2-blobs"
}

import {
  to = google_storage_bucket_iam_member.blobs_public_viewer
  id = "b/geodashing-v2-blobs/roles/storage.objectViewer/allUsers"
}

import {
  to = google_storage_bucket_iam_member.uploader_admin
  id = "b/geodashing-v2-blobs/roles/storage.objectAdmin/serviceAccount:geodashing-uploader@geodashing-v2.iam.gserviceaccount.com"
}

import {
  to = google_service_account.geodashing_uploader
  id = "projects/geodashing-v2/serviceAccounts/geodashing-uploader@geodashing-v2.iam.gserviceaccount.com"
}

import {
  to = google_project_iam_member.uploader_aiplatform_user
  id = "geodashing-v2 roles/aiplatform.user serviceAccount:geodashing-uploader@geodashing-v2.iam.gserviceaccount.com"
}

import {
  to = google_apikeys_key.backend_processing
  id = "projects/927002408097/locations/global/keys/a7f2aab3-6a7b-448b-92b0-c14afcf65fe4"
}

import {
  to = google_apikeys_key.backend_api_key
  id = "projects/927002408097/locations/global/keys/02c51582-f7d5-4b90-ade8-bfb3a1eb652c"
}

import {
  to = google_apikeys_key.ui_api_key
  id = "projects/927002408097/locations/global/keys/5b387efe-d0ea-4246-b7cf-09193bff1dea"
}
