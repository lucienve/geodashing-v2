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
     * Constructor.
     *
     * @param PDO $db The PDO connection instance.
     * @param string $apiKey The Google Maps API Key.
     */
    public function __construct(PDO $db, string $apiKey)
    {
        $this->db = $db;
        $this->apiKey = $apiKey;
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

        $url = sprintf("https://maps.googleapis.com/maps/api/geocode/json?latlng=%f,%f&key=%s", $lat, $lon, urlencode($this->apiKey));

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

        // Note: In MySQL 8 with SRID 4326, ST_X is Latitude, ST_Y is Longitude
        $sql = "
            SELECT 
                name, 
                admin_name, 
                country_name, 
                ST_X(location) as lat, 
                ST_Y(location) as lon,
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
}
