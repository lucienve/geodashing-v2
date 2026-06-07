<?php

declare(strict_types=1);

namespace App\Services;

use PDO;
use PDOException;

/**
 * Class GeoContextService
 *
 * Provides geographical context for Dashpoints using the Google Maps API
 * and a local major cities spatial database.
 */
class GeoContextService
{
    /**
     * @var PDO The configured database connection.
     */
    private PDO $db;

    /**
     * @var string The Google Maps API key.
     */
    private string $apiKey;

    /**
     * @var string The Google Maps API base URL.
     */
    private string $apiBaseUrl;

    /**
     * Constructor.
     *
     * @param PDO $db The PDO connection instance.
     * @param string $apiKey The Google Maps API Key.
     * @param string $apiBaseUrl The Google Maps API base URL.
     */
    public function __construct(PDO $db, string $apiKey, string $apiBaseUrl = 'https://maps.googleapis.com')
    {
        $this->db = $db;
        $this->apiKey = $apiKey;
        $this->apiBaseUrl = $apiBaseUrl;
    }

    /**
     * Generates a human-readable geographical context string for a Dashpoint.
     *
     * @param float $lat The latitude of the Dashpoint.
     * @param float $lon The longitude of the Dashpoint.
     * @param string $dashpointId The ID of the Dashpoint.
     * @return string The formatted context string.
     */
    public function getDashpointContext(float $lat, float $lon, string $dashpointId): string
    {
        $region = $this->getProvinceAndCountry($lat, $lon);
        $cityContext = '';

        $nearestCity = $this->getLargestNearbyCity($lat, $lon);

        if ($nearestCity) {
            $bearingStr = $this->calculateBearing((float)$nearestCity['lat'], (float)$nearestCity['lon'], $lat, $lon);
            $distanceMiles = (int) round($nearestCity['distance_meters'] * 0.000621371);

            $cityContext = sprintf(
                ", and is %d miles %s of %s, %s, %s",
                $distanceMiles,
                strtolower($bearingStr),
                $nearestCity['name'],
                $nearestCity['admin_name'],
                $nearestCity['country_name']
            );
        }

        if ($region) {
            return sprintf("%s is in %s, %s%s", $dashpointId, $region['province'], $region['country'], $cityContext);
        } else if ($nearestCity) {
            return sprintf("%s is %d miles %s of %s, %s, %s", $dashpointId, $distanceMiles ?? 0, strtolower($bearingStr ?? ''), $nearestCity['name'], $nearestCity['admin_name'], $nearestCity['country_name']);
        }

        return sprintf("%s is at coordinates %f, %f", $dashpointId, $lat, $lon);
    }

    /**
     * Fetches the total timezone offset in seconds for the given coordinates.
     * Uses the Google Maps Time Zone API.
     *
     * @param float $lat The latitude.
     * @param float $lon The longitude.
     * @param int|null $timestamp Optional timestamp for the timezone calculation. Defaults to current time.
     * @return int The total timezone offset in seconds (rawOffset + dstOffset). Returns 0 on failure.
     */
    public function getTimezoneOffset(float $lat, float $lon, ?int $timestamp = null): int
    {
        if (empty($this->apiKey)) {
            return 0;
        }

        $timestamp = $timestamp ?? time();
        $url = sprintf(
            "%s/maps/api/timezone/json?location=%f,%f&timestamp=%d&key=%s",
            $this->apiBaseUrl,
            $lat,
            $lon,
            $timestamp,
            urlencode($this->apiKey)
        );

        $ch = curl_init();
        curl_setopt($ch, CURLOPT_URL, $url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 5);
        $response = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        if ($httpCode !== 200 || !$response) {
            error_log("GeoContextService getTimezoneOffset failed with HTTP {$httpCode}");
            return 0;
        }

        $data = json_decode($response, true);
        if (!isset($data['status']) || $data['status'] !== 'OK') {
            $errorMessage = $data['errorMessage'] ?? 'Unknown Error';
            error_log("GeoContextService getTimezoneOffset API Error: {$errorMessage} (Status: {$data['status']})");
            return 0;
        }

        $rawOffset = isset($data['rawOffset']) ? (int) $data['rawOffset'] : 0;
        $dstOffset = isset($data['dstOffset']) ? (int) $data['dstOffset'] : 0;

        return $rawOffset + $dstOffset;
    }

    /**
     * Retrieves the state/province and country using Google Maps Reverse Geocoding API.
     *
     * @param float $lat
     * @param float $lon
     * @return array|null An array containing 'province' and 'country', or null on failure.
     */
    protected function getProvinceAndCountry(float $lat, float $lon): ?array
    {
        if (empty($this->apiKey)) {
            return null;
        }

        $url = sprintf("%s/maps/api/geocode/json?latlng=%f,%f&key=%s", $this->apiBaseUrl, $lat, $lon, urlencode($this->apiKey));

        $ch = curl_init();
        curl_setopt($ch, CURLOPT_URL, $url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 5);
        $response = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        if ($httpCode !== 200 || !$response) {
            return null;
        }

        $data = json_decode($response, true);
        if (!isset($data['status']) || $data['status'] !== 'OK' || empty($data['results'])) {
            return null;
        }

        $province = null;
        $country = null;

        foreach ($data['results'][0]['address_components'] as $component) {
            if (in_array('administrative_area_level_1', $component['types'])) {
                $province = $component['long_name'];
            }
            if (in_array('country', $component['types'])) {
                $country = $component['long_name'];
            }
        }

        if ($province && $country) {
            return ['province' => $province, 'country' => $country];
        }

        return null;
    }

    /**
     * Retrieves the largest city within roughly 100 miles using spatial queries.
     *
     * @param float $lat
     * @param float $lon
     * @param int $radiusMiles
     * @return array|null Array containing city details and distance, or null if none found.
     */
    protected function getLargestNearbyCity(float $lat, float $lon, int $radiusMiles = 100): ?array
    {
        // 100 miles = ~160934 meters
        $radiusMeters = $radiusMiles * 1609.344;

        $sql = "
            SELECT 
                name, 
                admin_name, 
                country_name, 
                ST_Latitude(location) as lat, 
                ST_Longitude(location) as lon,
                ST_Distance_Sphere(location, ST_GeomFromText(:point, 4326)) as distance_meters
            FROM major_cities
            WHERE ST_Distance_Sphere(location, ST_GeomFromText(:point_filter, 4326)) <= :radius
            ORDER BY population DESC
            LIMIT 1
        ";

        try {
            $stmt = $this->db->prepare($sql);
            $wkt = sprintf("POINT(%f %f)", $lat, $lon);
            $stmt->execute([
                'point' => $wkt,
                'point_filter' => $wkt,
                'radius' => $radiusMeters
            ]);

            $result = $stmt->fetch(PDO::FETCH_ASSOC);
            if ($result) {
                return $result;
            }
        } catch (PDOException $e) {
            error_log("GeoContextService getLargestNearbyCity Error: " . $e->getMessage());
        }

        return null;
    }

    /**
     * Calculates the cardinal bearing from point 1 to point 2.
     *
     * @param float $lat1 City latitude
     * @param float $lon1 City longitude
     * @param float $lat2 Dashpoint latitude
     * @param float $lon2 Dashpoint longitude
     * @return string The cardinal direction (e.g., "Northwest")
     */
    protected function calculateBearing(float $lat1, float $lon1, float $lat2, float $lon2): string
    {
        $lat1 = deg2rad($lat1);
        $lon1 = deg2rad($lon1);
        $lat2 = deg2rad($lat2);
        $lon2 = deg2rad($lon2);

        $dLon = $lon2 - $lon1;

        $y = sin($dLon) * cos($lat2);
        $x = cos($lat1) * sin($lat2) - sin($lat1) * cos($lat2) * cos($dLon);

        $brng = atan2($y, $x);
        $brng = rad2deg($brng);
        $brng = fmod(($brng + 360), 360);
        if ($brng < 0) {
            $brng += 360;
        }

        $directions = [
            "North", "Northeast", "East", "Southeast",
            "South", "Southwest", "West", "Northwest", "North"
        ];

        $index = (int) round($brng / 45);
        return $directions[$index];
    }

    /**
     * Fetches the elevation for the given coordinates using the Google Maps Elevation API.
     *
     * @param float $lat The latitude.
     * @param float $lon The longitude.
     * @return float|null The elevation in meters, or null on failure.
     */
    public function getElevation(float $lat, float $lon): ?float
    {
        if (empty($this->apiKey)) {
            return null;
        }

        $url = sprintf(
            "%s/maps/api/elevation/json?locations=%f,%f&key=%s",
            $this->apiBaseUrl,
            $lat,
            $lon,
            urlencode($this->apiKey)
        );

        $ch = curl_init();
        curl_setopt($ch, CURLOPT_URL, $url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 5);
        $response = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        if ($httpCode !== 200 || !$response) {
            error_log("GeoContextService getElevation failed with HTTP {$httpCode}");
            return null;
        }

        $data = json_decode($response, true);
        if (!isset($data['status']) || $data['status'] !== 'OK' || empty($data['results'])) {
            $errorMessage = $data['errorMessage'] ?? 'Unknown Error';
            error_log("GeoContextService getElevation API Error: {$errorMessage} (Status: " . ($data['status'] ?? 'None') . ")");
            return null;
        }

        return isset($data['results'][0]['elevation']) ? (float) $data['results'][0]['elevation'] : null;
    }

    /**
     * Evaluates whether the given dashpoint is a new geographical extreme and returns an annotation string if so.
     *
     * @param string $dashpointId
     * @param float $lat
     * @param float $lon
     * @param float|null $elevation
     * @param string $stateProvince
     * @param string $countryCode
     * @param int $visitYear
     * @return string
     */
    public function evaluateAndGetExtremeAnnotations(string $dashpointId, float $lat, float $lon, ?float $elevation, string $stateProvince, string $countryCode, int $visitYear): string
    {
        $annotations = [];

        $metrics = [
            'northernmost' => ['value' => $lat, 'compare' => '>'],
            'southernmost' => ['value' => $lat, 'compare' => '<'],
            'easternmost' => ['value' => $lon, 'compare' => '>'],
            'westernmost' => ['value' => $lon, 'compare' => '<'],
        ];

        if ($elevation !== null) {
            $metrics['highest'] = ['value' => $elevation, 'compare' => '>'];
            $metrics['lowest'] = ['value' => $elevation, 'compare' => '<'];
        }

        foreach ($metrics as $type => $data) {
            $value = $data['value'];
            $compare = $data['compare'];

            // Check All-Time and Yearly
            foreach ([null, $visitYear] as $year) {
                $timeScope = ($year === null) ? 'all-time' : "{$year}";

                $yearCondition = ($year === null) ? "year IS NULL" : "year = :year";
                $params = [
                    'cc' => $countryCode,
                    'sp' => $stateProvince,
                    'type' => $type
                ];
                if ($year !== null) {
                    $params['year'] = $year;
                }

                $stmt = $this->db->prepare("SELECT id, dashpoint_id, coordinate_value FROM regional_extremes WHERE country_code = :cc AND state_province = :sp AND $yearCondition AND extreme_type = :type LIMIT 1");
                $stmt->execute($params);
                $currentRecord = $stmt->fetch(PDO::FETCH_ASSOC);

                $isNewRecord = false;
                if (!$currentRecord) {
                    $isNewRecord = true;
                } else {
                    $currentValue = (float) $currentRecord['coordinate_value'];
                    if ($compare === '>' && $value > $currentValue) {
                        $isNewRecord = true;
                    } elseif ($compare === '<' && $value < $currentValue) {
                        $isNewRecord = true;
                    }
                }

                if ($isNewRecord) {
                    // It's a new record!
                    $annotations[] = "the {$timeScope} {$type} dashpoint found in {$stateProvince}";

                    if ($currentRecord) {
                        $updateStmt = $this->db->prepare("UPDATE regional_extremes SET dashpoint_id = :dpid, coordinate_value = :val, created_at = NOW() WHERE id = :id");
                        $updateStmt->execute([
                            'dpid' => $dashpointId,
                            'val' => $value,
                            'id' => $currentRecord['id']
                        ]);
                    } else {
                        $insertParams = [
                            'cc' => $countryCode,
                            'sp' => $stateProvince,
                            'year' => $year,
                            'type' => $type,
                            'dpid' => $dashpointId,
                            'val' => $value
                        ];
                        $insertStmt = $this->db->prepare("INSERT INTO regional_extremes (country_code, state_province, year, extreme_type, dashpoint_id, coordinate_value) VALUES (:cc, :sp, :year, :type, :dpid, :val)");
                        $insertStmt->execute($insertParams);
                    }
                }
            }
        }

        if (empty($annotations)) {
            return '';
        }

        if (count($annotations) === 1) {
            return ", and is " . $annotations[0];
        }

        $last = array_pop($annotations);
        return ", and is " . implode(", ", $annotations) . " and " . $last;
    }
}
