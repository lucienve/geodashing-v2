"""Module for relocating a geodashing point within a given radius on dry land."""

import argparse
import json
import math
import sys

import geopandas as gpd
import numpy as np
import shapely
import shapely.geometry

import backend.scripts.generate_game

# Mean radius of the Earth in kilometers
EARTH_RADIUS_KM: float = 6371.0

# Kilometers per degree of latitude: (2 * pi * R) / 360 degrees (~111.19 km/deg)
KM_PER_DEGREE_LAT: float = (2.0 * math.pi * EARTH_RADIUS_KM) / 360.0

# Minimum cos(latitude) floor to prevent ZeroDivisionError at Earth's poles (+/-90 deg)
MIN_COS_LAT_FLOOR: float = 0.01


# Minimum relocation distance in kilometers (100 meters) to ensure a distinct new coordinate
MIN_REROLL_RADIUS_KM: float = 0.1


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates the Great Circle distance between two points in kilometers."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_KM * c


def is_valid_land_point(
    lat: float,
    lon: float,
    spatial_filter: backend.scripts.generate_game.SpatialFilter
) -> bool:
    """Evaluates whether a single (lat, lon) coordinate lands on dry land and not in a lake."""
    point = shapely.geometry.Point(lon, lat)
    gdf = gpd.GeoDataFrame(geometry=[point], crs="EPSG:4326")
    proj_points = gdf.to_crs(epsg=6933)

    proj_buffers = shapely.buffer(proj_points.geometry, 100)
    land_map, lake_map = spatial_filter.get_candidate_matches(proj_buffers)

    if 0 in land_map:
        buffer_geom = proj_buffers[0]
        matching_lands = land_map[0]
        matching_lakes = lake_map.get(0, [])
        return spatial_filter.eval_boundary_point(buffer_geom, matching_lands, matching_lakes)

    return False


def generate_polar_candidate(
    origin: tuple[float, float],
    min_radius_km: float = MIN_REROLL_RADIUS_KM,
    max_radius_km: float = 10.0
) -> tuple[float, float]:
    """Generates a single random coordinate uniformly distributed in the annulus
    between min and max radius."""

    origin_lat_deg, origin_lon_deg = origin
    origin_lat_rad = math.radians(origin_lat_deg)
    origin_lon_rad = math.radians(origin_lon_deg)

    # Uniform areal sampling in circular annulus: r = sqrt(u * (r_max^2 - r_min^2) + r_min^2)
    rand_fraction = np.random.uniform(0.0, 1.0)
    sample_distance_km = math.sqrt(
        rand_fraction * (max_radius_km**2 - min_radius_km**2) + min_radius_km**2
    )

    angular_distance_rad = sample_distance_km / EARTH_RADIUS_KM
    bearing_rad = np.random.uniform(0.0, 2.0 * math.pi)

    # Great-circle direct destination formula
    cand_lat_rad = math.asin(
        math.sin(origin_lat_rad) * math.cos(angular_distance_rad) +
        math.cos(origin_lat_rad) * math.sin(angular_distance_rad) * math.cos(bearing_rad)
    )
    cand_lon_rad = origin_lon_rad + math.atan2(
        math.sin(bearing_rad) * math.sin(angular_distance_rad) * math.cos(origin_lat_rad),
        math.cos(angular_distance_rad) - math.sin(origin_lat_rad) * math.sin(cand_lat_rad)
    )

    cand_lat_deg = math.degrees(cand_lat_rad)
    cand_lon_deg = (math.degrees(cand_lon_rad) + 540.0) % 360.0 - 180.0
    return cand_lat_deg, cand_lon_deg



def find_valid_reroll_point(
    origin: tuple[float, float],
    max_radius_km: float = 10.0,
    spatial_filter: backend.scripts.generate_game.SpatialFilter | None = None,
    max_attempts: int = 2000,
    verbose: bool = False
) -> tuple[float, float]:
    """Finds a new random point within max_radius_km that satisfies dry land constraints."""
    if spatial_filter is None:
        spatial_filter = backend.scripts.generate_game.build_spatial_filter(
            "data/ne_10m_land.zip", "data/ne_10m_lakes.zip", verbose
        )

    for _ in range(max_attempts):
        lat_f, lon_f = generate_polar_candidate(origin, MIN_REROLL_RADIUS_KM, max_radius_km)
        if is_valid_land_point(lat_f, lon_f, spatial_filter):
            return lat_f, lon_f

    msg = (
        f"Could not find a valid land point within {max_radius_km} km of {origin} "
        f"after {max_attempts} attempts."
    )
    raise RuntimeError(msg)



def main() -> None:
    """CLI entrypoint for rerolling a dashpoint location."""
    parser = argparse.ArgumentParser(description="Reroll a dashpoint location on dry land.")
    parser.add_argument("--lat", type=float, required=True, help="Origin latitude")
    parser.add_argument("--lon", type=float, required=True, help="Origin longitude")
    parser.add_argument(
        "--max-radius-km", type=float, default=10.0, help="Maximum relocation radius in km"
    )
    parser.add_argument(
        "--land-zip", type=str, default="data/ne_10m_land.zip", help="Path to land shapefile"
    )
    parser.add_argument(
        "--lakes-zip", type=str, default="data/ne_10m_lakes.zip", help="Path to lakes shapefile"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print debug/progress messages to stdout"
    )

    args = parser.parse_args()

    try:
        spatial_filter = backend.scripts.generate_game.build_spatial_filter(
            args.land_zip, args.lakes_zip, args.verbose
        )
        new_lat, new_lon = find_valid_reroll_point(
            (args.lat, args.lon), args.max_radius_km, spatial_filter, verbose=args.verbose
        )

        output = {
            "status": "success",
            "lat": new_lat,
            "lon": new_lon
        }
        print(json.dumps(output))
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        output = {
            "status": "error",
            "message": str(e)
        }
        print(json.dumps(output), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
