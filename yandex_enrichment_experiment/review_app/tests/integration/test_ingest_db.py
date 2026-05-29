import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

# Skip all tests if testcontainers not available
pytest.importorskip("testcontainers")


class TestBootstrapSchema:
    @pytest.mark.asyncio
    async def test_bootstrap_schema_creates_table_and_extension(self, pg_session):
        """Test that bootstrap_schema creates table and pg_trgm extension."""
        from sqlalchemy import text

        async with pg_session.connection() as conn:
            # Check that pg_trgm extension exists
            result = await conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'pg_trgm'")
            )
            rows = result.fetchall()
            assert len(rows) > 0, "pg_trgm extension not created"

            # Check that research_cards table exists
            result = await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_name = 'research_cards'"
                )
            )
            rows = result.fetchall()
            assert len(rows) > 0, "research_cards table not created"


class TestUpsertCard:
    @pytest.mark.asyncio
    async def test_upsert_inserts_new_row(self, pg_session):
        """Test that upsert_card inserts a new row from local format."""
        from review_app.ingest import to_row, upsert_card
        import json

        fixture_path = Path(__file__).parent.parent / "fixtures" / "sample_local.json"
        with open(fixture_path, encoding="utf-8") as f:
            payload = json.load(f)

        mtime = datetime(2026, 5, 30, 10, 0, 0)
        source_file = Path("test_data/1000341388__local.json")

        row = to_row(payload, source_file, mtime)
        await upsert_card(pg_session, row)

        # Verify row was inserted
        from sqlalchemy import select, text
        from review_app.models import ResearchCard

        result = await pg_session.execute(
            select(ResearchCard).where(
                ResearchCard.oid == "1000341388",
                ResearchCard.model_key == "local"
            )
        )
        cards = result.scalars().all()
        assert len(cards) == 1
        card = cards[0]
        assert card.name == "Адвокат Фремм"
        assert card.critic_score == 9.0

    @pytest.mark.asyncio
    async def test_upsert_is_idempotent(self, pg_session):
        """Test that upserting the same row twice results in one row."""
        from review_app.ingest import to_row, upsert_card
        import json

        fixture_path = Path(__file__).parent.parent / "fixtures" / "sample_local.json"
        with open(fixture_path, encoding="utf-8") as f:
            payload = json.load(f)

        mtime = datetime(2026, 5, 30, 10, 0, 0)
        source_file = Path("test_data/1000341388__local.json")

        row = to_row(payload, source_file, mtime)

        # Upsert twice
        await upsert_card(pg_session, row)
        await upsert_card(pg_session, row)

        # Verify only one row exists
        from sqlalchemy import select
        from review_app.models import ResearchCard

        result = await pg_session.execute(
            select(ResearchCard).where(
                ResearchCard.oid == "1000341388",
                ResearchCard.model_key == "local"
            )
        )
        cards = result.scalars().all()
        assert len(cards) == 1

    @pytest.mark.asyncio
    async def test_upsert_updates_when_mtime_changes(self, pg_session):
        """Test that upsert updates row when file mtime is newer."""
        from review_app.ingest import to_row, upsert_card
        import json

        fixture_path = Path(__file__).parent.parent / "fixtures" / "sample_local.json"
        with open(fixture_path) as f:
            payload = json.load(f)

        # First upsert with earlier mtime
        mtime1 = datetime(2026, 5, 30, 10, 0, 0)
        source_file = Path("test_data/test_update__local.json")
        row1 = to_row(payload, source_file, mtime1)
        row1["oid"] = "test_update"
        await upsert_card(pg_session, row1)

        # Modify payload and upsert with later mtime
        payload_modified = json.loads(json.dumps(payload))
        payload_modified["tokens"]["grand_total"] = 99999
        mtime2 = datetime(2026, 5, 30, 11, 0, 0)
        row2 = to_row(payload_modified, source_file, mtime2)
        row2["oid"] = "test_update"
        await upsert_card(pg_session, row2)

        # Verify row was updated
        from sqlalchemy import select
        from review_app.models import ResearchCard

        result = await pg_session.execute(
            select(ResearchCard).where(
                ResearchCard.oid == "test_update",
                ResearchCard.model_key == "local"
            )
        )
        cards = result.scalars().all()
        assert len(cards) == 1
        assert cards[0].tokens_total == 99999

    @pytest.mark.asyncio
    async def test_upsert_preserves_review_status_edited(self, pg_session):
        """Test that upsert preserves review_status='edited' and operator_notes."""
        from review_app.ingest import to_row, upsert_card
        from sqlalchemy import select, update
        from review_app.models import ResearchCard
        import json

        fixture_path = Path(__file__).parent.parent / "fixtures" / "sample_local.json"
        with open(fixture_path) as f:
            payload = json.load(f)

        # First upsert
        mtime1 = datetime(2026, 5, 30, 10, 0, 0)
        source_file = Path("test_data/test_edited__local.json")
        row1 = to_row(payload, source_file, mtime1)
        row1["oid"] = "test_edited"
        await upsert_card(pg_session, row1)

        # Manually set review_status to 'edited' and add operator notes
        await pg_session.execute(
            update(ResearchCard)
            .where(
                ResearchCard.oid == "test_edited",
                ResearchCard.model_key == "local"
            )
            .values(
                review_status="edited",
                operator_notes="hand-edited"
            )
        )
        await pg_session.commit()

        # Upsert again with NEWER mtime but altered card
        payload_modified = json.loads(json.dumps(payload))
        payload_modified["submitted_card"]["what_they_do"] = "MODIFIED TEXT"
        mtime2 = datetime(2026, 5, 30, 11, 0, 0)
        row2 = to_row(payload_modified, source_file, mtime2)
        row2["oid"] = "test_edited"
        await upsert_card(pg_session, row2)

        # Verify: card must be UNCHANGED, review_status must still be 'edited'
        result = await pg_session.execute(
            select(ResearchCard).where(
                ResearchCard.oid == "test_edited",
                ResearchCard.model_key == "local"
            )
        )
        cards = result.scalars().all()
        assert len(cards) == 1
        card = cards[0]

        # Card should not have been updated
        assert card.card["what_they_do"] != "MODIFIED TEXT"
        assert "Юридическая фирма" in card.card["what_they_do"]

        # Review status and notes should be preserved
        assert card.review_status == "edited"
        assert card.operator_notes == "hand-edited"


class TestIngestDirectory:
    @pytest.mark.asyncio
    async def test_ingest_directory_counts(self, pg_session):
        """Test that ingest_directory processes multiple files correctly."""
        from review_app.ingest import ingest_directory
        import json

        fixture_path = Path(__file__).parent.parent / "fixtures" / "sample_local.json"
        with open(fixture_path) as f:
            payload = json.load(f)

        # Create temporary directory with two different oids
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create first file
            payload1 = json.loads(json.dumps(payload))
            payload1["oid"] = "oid_1"
            file1 = tmppath / "oid_1__local.json"
            with open(file1, "w") as f:
                json.dump(payload1, f)

            # Create second file
            payload2 = json.loads(json.dumps(payload))
            payload2["oid"] = "oid_2"
            file2 = tmppath / "oid_2__local.json"
            with open(file2, "w") as f:
                json.dump(payload2, f)

            # Ingest directory
            result = await ingest_directory(pg_session, tmppath)

            assert result["processed"] == 2
            assert result["skipped"] == 0
            assert result["errors"] == 0

            # Verify both rows were inserted
            from sqlalchemy import select
            from review_app.models import ResearchCard

            rows = await pg_session.execute(select(ResearchCard))
            cards = rows.scalars().all()
            assert len(cards) == 2
            oids = {card.oid for card in cards}
            assert oids == {"oid_1", "oid_2"}
