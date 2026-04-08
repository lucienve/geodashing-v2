<?php
$dashpointId = "../../../etc";
$safeDashpointId = preg_replace('/[^a-zA-Z0-9_-]/', '', $dashpointId);
echo $safeDashpointId;
