import sqlite3

from bii.local_store import LocalValidationStore


def test_v024_exposure_table_is_upgraded_without_losing_rows(tmp_path):
    path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE spatial_exposure_sources (
            source_name TEXT PRIMARY KEY,
            authority TEXT NOT NULL,
            methodology_note TEXT NOT NULL,
            source_reference TEXT,
            imported_at TEXT NOT NULL
        );
        CREATE TABLE spatial_exposure_observations (
            exposure_observation_id INTEGER PRIMARY KEY,
            source_name TEXT NOT NULL REFERENCES spatial_exposure_sources(source_name),
            domain TEXT NOT NULL CHECK(domain IN (
                'CLIMATE_HAZARD','TRANSPORT_ACCESS','POWER_SYSTEM','ENVIRONMENTAL_REGULATORY'
            )),
            metric_code TEXT NOT NULL,
            metric_label TEXT NOT NULL,
            spatial_scope TEXT NOT NULL CHECK(spatial_scope IN ('SITE','UPAZILA','DISTRICT')),
            establishment_ref TEXT,
            district TEXT,
            upazila TEXT,
            value_text TEXT,
            value_numeric REAL,
            unit TEXT,
            direction TEXT NOT NULL CHECK(direction IN (
                'HIGHER_MEANS_MORE_EXPOSURE','HIGHER_MEANS_LESS_EXPOSURE','CONTEXT_ONLY'
            )),
            source_vintage TEXT,
            observed_at TEXT,
            evidence_note TEXT,
            observation_sha256 TEXT NOT NULL,
            UNIQUE(source_name, observation_sha256)
        );
        INSERT INTO spatial_exposure_sources(
            source_name, authority, methodology_note, imported_at
        ) VALUES('Legacy Source','Test','Legacy fixture','2026-09-24T00:00:00+06:00');
        INSERT INTO spatial_exposure_observations(
            source_name, domain, metric_code, metric_label, spatial_scope,
            district, value_text, direction, observed_at, observation_sha256
        ) VALUES(
            'Legacy Source','CLIMATE_HAZARD','FLOOD','Flood context','DISTRICT',
            'Gazipur','Elevated','CONTEXT_ONLY','2026-09-24','legacy-hash'
        );
        """
    )
    conn.commit()
    conn.close()

    with LocalValidationStore(path) as store:
        row = store.conn.execute(
            """SELECT domain, metric_code, canonical_geo_ref
               FROM spatial_exposure_observations
               WHERE observation_sha256='legacy-hash'"""
        ).fetchone()
        assert row["domain"] == "CLIMATE_HAZARD"
        assert row["metric_code"] == "FLOOD"
        assert row["canonical_geo_ref"] is None

        store.record_spatial_exposure_source(
            "New Source",
            authority="Test",
            methodology_note="v0.25 upgrade test",
            imported_at="2026-09-24T01:00:00+06:00",
        )
        inserted = store.ingest_spatial_exposure_observations(
            "New Source",
            [{
                "domain": "DISASTER_RISK",
                "metric_code": "RISK",
                "metric_label": "Risk category",
                "spatial_scope": "DISTRICT",
                "district": "Gazipur",
                "value_text": "Low",
                "direction": "CONTEXT_ONLY",
                "observed_at": "2026-09-24",
                "canonical_geo_ref": "BBS:DIST:30:33",
                "geography_match_type": "EXACT_NAME",
            }],
        )
        assert inserted == 1
