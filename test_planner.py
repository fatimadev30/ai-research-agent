"""Unit tests for the research planner."""

import pytest
from services.research_planner import parse_prompt, ResearchPlan


class TestResearchPlanner:
    def test_basic_prompt(self):
        plan = parse_prompt("Find 50 AI companies in Pakistan. Collect name, website, email, and LinkedIn URL.")
        assert plan.target_count == 50
        assert "name" in plan.fields
        assert "website" in plan.fields
        assert "email" in plan.fields
        assert "linkedin_url" in plan.fields
        assert "source_url" in plan.fields  # Always added.
        assert plan.geography.lower() == "pakistan"
        assert len(plan.search_queries) >= 2

    def test_default_count(self):
        plan = parse_prompt("Find coffee shops in Berlin. Collect name and website.")
        assert plan.target_count == 50  # Default.

    def test_max_count_cap(self):
        plan = parse_prompt("Find 9999 companies. Collect name.")
        assert plan.target_count <= 500  # Capped.

    def test_empty_prompt_raises(self):
        with pytest.raises(ValueError):
            parse_prompt("")

    def test_fields_extraction(self):
        plan = parse_prompt("Find professors. Collect name, university, department, research interests, email, and publications.")
        assert "name" in plan.fields
        assert "university" in plan.fields
        assert "department" in plan.fields
        assert "research_interests" in plan.fields
        assert "email" in plan.fields
        assert "publications" in plan.fields

    def test_dedup_keys(self):
        plan = parse_prompt("Find 30 companies. Collect name, website, and email.")
        assert "name" in plan.dedup_keys

    def test_search_queries_unique(self):
        plan = parse_prompt("Find 100 AI companies in Pakistan. Collect name and website.")
        assert len(plan.search_queries) == len(set(plan.search_queries))

    def test_export_format(self):
        plan = parse_prompt("Find 10 items. Collect name.", export_format="csv")
        assert plan.export_format == "csv"

    def test_to_dict(self):
        plan = parse_prompt("Find 10 items. Collect name.")
        d = plan.to_dict()
        assert "prompt" in d
        assert "fields" in d
        assert "target_count" in d
        assert isinstance(d["search_queries"], list)
