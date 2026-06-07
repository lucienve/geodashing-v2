<?php

/**
 * Mock Google Maps API Endpoint for E2E Tests
 *
 * Simulates response structures expected from Google Maps Platform APIs.
 */

declare(strict_types=1);

header('Content-Type: application/json');

$requestUri = $_SERVER['REQUEST_URI'] ?? '';
$queryString = $_SERVER['QUERY_STRING'] ?? '';

// Parse query string correctly to handle nested path query parameters
$params = [];
if (strpos($queryString, '?') !== false) {
    $parts = explode('?', $queryString);
    $actualQuery = end($parts);
    parse_str($actualQuery, $params);
} else {
    parse_str($queryString, $params);
}

// Validate the required API key
$key = $params['key'] ?? '';
if (empty($key)) {
    http_response_code(400);
    echo json_encode([
        'status' => 'REQUEST_DENIED',
        'errorMessage' => 'The provided API key is invalid or missing.'
    ]);
    exit;
}

// 1. Time Zone API Mock
// Emulates the JSON response structure for timezone offsets relative to UTC.
// Reference: https://developers.google.com/maps/documentation/timezone/overview
if (strpos($requestUri, 'timezone') !== false) {
    $allowedParams = ['location', 'timestamp', 'key'];
    $actualParams = array_keys($params);
    $invalidParams = array_diff($actualParams, $allowedParams);

    if (!empty($invalidParams)) {
        http_response_code(400);
        echo json_encode([
            'status' => 'INVALID_REQUEST',
            'errorMessage' => 'Invalid or unknown parameter(s): ' . implode(', ', $invalidParams)
        ]);
        exit;
    }

    if (!isset($params['location']) || !isset($params['timestamp'])) {
        http_response_code(400);
        echo json_encode([
            'status' => 'INVALID_REQUEST',
            'errorMessage' => 'Missing required parameter: location or timestamp'
        ]);
        exit;
    }

    $location = $params['location'];
    $timestamp = $params['timestamp'];

    if (empty($location) || empty($timestamp)) {
        http_response_code(400);
        echo json_encode([
            'status' => 'INVALID_REQUEST',
            'errorMessage' => 'Parameter location or timestamp cannot be empty'
        ]);
        exit;
    }

    // Validate location matches "lat,lng" format (numeric values)
    if (!preg_match('/^-?\d+(\.\d+)?,-?\d+(\.\d+)?$/', $location)) {
        http_response_code(400);
        echo json_encode([
            'status' => 'INVALID_REQUEST',
            'errorMessage' => 'Invalid location format. Expected "latitude,longitude".'
        ]);
        exit;
    }

    // Validate timestamp is a valid integer
    if (!preg_match('/^-?\d+$/', (string)$timestamp)) {
        http_response_code(400);
        echo json_encode([
            'status' => 'INVALID_REQUEST',
            'errorMessage' => 'Invalid timestamp format. Expected an integer.'
        ]);
        exit;
    }

    echo json_encode([
        'status' => 'OK',
        'rawOffset' => -18000,
        'dstOffset' => 0
    ]);
// 2. Elevation API Mock
// Emulates the elevation data in meters above sea level for specific coordinates.
// Reference: https://developers.google.com/maps/documentation/elevation/overview
} elseif (strpos($requestUri, 'elevation') !== false) {
    $allowedParams = ['locations', 'key'];
    $actualParams = array_keys($params);
    $invalidParams = array_diff($actualParams, $allowedParams);

    if (!empty($invalidParams)) {
        http_response_code(400);
        echo json_encode([
            'status' => 'INVALID_REQUEST',
            'errorMessage' => 'Invalid or unknown parameter(s): ' . implode(', ', $invalidParams)
        ]);
        exit;
    }

    if (!isset($params['locations'])) {
        http_response_code(400);
        echo json_encode([
            'status' => 'INVALID_REQUEST',
            'errorMessage' => 'Missing required parameter: locations'
        ]);
        exit;
    }

    $locations = $params['locations'];

    if (empty($locations)) {
        http_response_code(400);
        echo json_encode([
            'status' => 'INVALID_REQUEST',
            'errorMessage' => 'Parameter locations cannot be empty'
        ]);
        exit;
    }

    // Validate locations matches "lat,lng" format (numeric values, optional pipe separator)
    $coordPairs = explode('|', $locations);
    foreach ($coordPairs as $pair) {
        if (!preg_match('/^-?\d+(\.\d+)?,-?\d+(\.\d+)?$/', $pair)) {
            http_response_code(400);
            echo json_encode([
                'status' => 'INVALID_REQUEST',
                'errorMessage' => 'Invalid locations format. Expected "latitude,longitude" separated by pipe symbols.'
            ]);
            exit;
        }
    }

    echo json_encode([
        'status' => 'OK',
        'results' => [
            [
                'elevation' => 250.0
            ]
        ]
    ]);
// 3. Geocoding API Mock
// Emulates reverse geocoding address components containing state/province and country details.
// Reference: https://developers.google.com/maps/documentation/geocoding/overview
} elseif (strpos($requestUri, 'geocode') !== false) {
    $allowedParams = ['latlng', 'key'];
    $actualParams = array_keys($params);
    $invalidParams = array_diff($actualParams, $allowedParams);

    if (!empty($invalidParams)) {
        http_response_code(400);
        echo json_encode([
            'status' => 'INVALID_REQUEST',
            'errorMessage' => 'Invalid or unknown parameter(s): ' . implode(', ', $invalidParams)
        ]);
        exit;
    }

    if (!isset($params['latlng'])) {
        http_response_code(400);
        echo json_encode([
            'status' => 'INVALID_REQUEST',
            'errorMessage' => 'Missing required parameter: latlng'
        ]);
        exit;
    }

    $latlng = $params['latlng'];

    if (empty($latlng)) {
        http_response_code(400);
        echo json_encode([
            'status' => 'INVALID_REQUEST',
            'errorMessage' => 'Parameter latlng cannot be empty'
        ]);
        exit;
    }

    // Validate latlng matches "lat,lng" format (numeric values)
    if (!preg_match('/^-?\d+(\.\d+)?,-?\d+(\.\d+)?$/', $latlng)) {
        http_response_code(400);
        echo json_encode([
            'status' => 'INVALID_REQUEST',
            'errorMessage' => 'Invalid latlng format. Expected "latitude,longitude".'
        ]);
        exit;
    }

    echo json_encode([
        'status' => 'OK',
        'results' => [
            [
                'address_components' => [
                    [
                        'long_name' => 'Wisconsin',
                        'types' => ['administrative_area_level_1']
                    ],
                    [
                        'long_name' => 'United States',
                        'types' => ['country']
                    ]
                ]
            ]
        ]
    ]);
} else {
    http_response_code(400);
    echo json_encode([
        'status' => 'REQUEST_DENIED',
        'errorMessage' => 'Invalid mock endpoint requested.'
    ]);
}
