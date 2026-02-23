"""
Team Name Mapping Utilities
Maps external team names/IDs to canonical Team records
Supports fuzzy matching and manual overrides
"""

import re
import yaml
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from rapidfuzz import fuzz, process
from django.conf import settings
from django.db import transaction

from core.models import Team, TeamExternalId

logger = logging.getLogger(__name__)


class TeamMapper:
    """
    Maps external team names/IDs to canonical Team records
    Handles fuzzy matching, aliases, and manual overrides
    """
    
    def __init__(self, source: str, override_file: Optional[str] = None):
        """
        Args:
            source: Data source name ('ncaa', 'espn', etc.)
            override_file: Path to YAML override file (default: backend/team_alias_overrides.yml)
        """
        self.source = source
        self.teams = {t.id: t for t in Team.objects.all()}
        self.overrides = {}
        self.ncaa_mappings = {}
        self.unmatched = []
        
        # Load NCAA comprehensive mappings (NEW - highest priority)
        ncaa_mappings_file = Path(settings.BASE_DIR) / 'ncaa_team_name_mappings.yml'
        if ncaa_mappings_file.exists() and source == 'ncaa':
            self._load_ncaa_mappings(ncaa_mappings_file)
        
        # Load overrides (fallback for other sources or special cases)
        if override_file is None:
            override_file = Path(settings.BASE_DIR) / 'team_alias_overrides.yml'
        
        self.override_file = Path(override_file)
        if self.override_file.exists():
            self._load_overrides()
        
        # Build search index from team names and aliases
        self._build_search_index()
    
    def _load_overrides(self):
        """Load manual team name mappings from YAML file"""
        try:
            with open(self.override_file, 'r') as f:
                data = yaml.safe_load(f) or {}
                self.overrides = data.get(self.source, {})
            logger.info(f"Loaded {len(self.overrides)} team overrides for {self.source}")
        except Exception as e:
            logger.warning(f"Could not load overrides from {self.override_file}: {e}")
    
    def _load_ncaa_mappings(self, mappings_file: Path):
        """Load comprehensive NCAA team name mappings from YAML file"""
        try:
            with open(mappings_file, 'r') as f:
                data = yaml.safe_load(f) or {}
                self.ncaa_mappings = data.get('ncaa', {})
            logger.info(f"Loaded {len(self.ncaa_mappings)} NCAA team name mappings")
        except Exception as e:
            logger.warning(f"Could not load NCAA mappings from {mappings_file}: {e}")
    
    def _build_search_index(self):
        """Build searchable index of team names and aliases"""
        self.search_index = {}
        for team_id, team in self.teams.items():
            # Add main name
            self.search_index[self._normalize(team.name)] = team_id
            
            # Add aliases
            if team.aliases:
                for alias in team.aliases:
                    self.search_index[self._normalize(alias)] = team_id
    
    @staticmethod
    def _normalize(name: str) -> str:
        """Normalize team name for matching"""
        if not name:
            return ""
        
        # Lowercase
        name = name.lower()
        
        # Remove common suffixes/prefixes
        name = re.sub(r'\b(university|state|college|the)\b', '', name)
        
        # Remove special chars, extra spaces
        name = re.sub(r'[^\w\s]', '', name)
        name = re.sub(r'\s+', ' ', name)
        
        return name.strip()
    
    def find_team(
        self,
        external_name: str,
        external_id: Optional[str] = None,
        min_confidence: float = 0.98,
    ) -> Tuple[Optional[Team], float, bool]:
        """
        Find matching Team for external name/ID
        
        Args:
            external_name: Team name from external source
            external_id: Optional external ID
            min_confidence: Minimum fuzzy match score (0.0-1.0)
        
        Returns:
            (Team, confidence, is_manual_override)
            Returns (None, 0.0, False) if no good match found
        """
        # PRIORITY 1: Check comprehensive NCAA mappings (for NCAA source)
        if self.source == 'ncaa':
            if external_name in self.ncaa_mappings:
                canonical_name = self.ncaa_mappings[external_name]
                team = Team.objects.filter(name=canonical_name).first()
                if team:
                    logger.debug(f"NCAA exact match: '{external_name}' -> '{canonical_name}'")
                    return (team, 1.0, True)
                else:
                    logger.warning(f"NCAA mapping '{canonical_name}' not found in Team table for '{external_name}'")
            else:
                # For NCAA source, if not in comprehensive mappings, reject it
                # This prevents non-D1 teams from being fuzzy matched
                logger.info(f"NCAA team '{external_name}' not in comprehensive D1 mappings - skipping")
                return (None, 0.0, False)
        
        # PRIORITY 2: Check manual overrides (try both ID and name)
        if external_id and external_id in self.overrides:
            canonical_name = self.overrides[external_id]
            team = Team.objects.filter(name=canonical_name).first()
            if team:
                logger.debug(f"Override match (by ID): '{external_id}' -> '{canonical_name}'")
                return (team, 1.0, True)
        
        if external_name in self.overrides:
            canonical_name = self.overrides[external_name]
            team = Team.objects.filter(name=canonical_name).first()
            if team:
                logger.debug(f"Override match (by name): '{external_name}' -> '{canonical_name}'")
                return (team, 1.0, True)
            else:
                logger.warning(f"Override '{canonical_name}' not found in Team table")
        
        # PRIORITY 3: Try exact normalized match
        normalized = self._normalize(external_name)
        if normalized in self.search_index:
            team_id = self.search_index[normalized]
            logger.debug(f"Exact normalized match: '{external_name}' -> '{self.teams[team_id].name}'")
            return (self.teams[team_id], 1.0, False)
        
        # PRIORITY 4: Fuzzy match against all team names (LAST RESORT)
        all_names = [(self._normalize(t.name), t.id) for t in self.teams.values()]
        
        # Use rapidfuzz to find best match
        result = process.extractOne(
            normalized,
            [name for name, _ in all_names],
            scorer=fuzz.ratio
        )
        
        if result:
            match_name, score, _ = result
            confidence = score / 100.0  # Convert to 0.0-1.0
            
            if confidence >= min_confidence:
                # Find the team ID
                team_id = next(tid for name, tid in all_names if name == match_name)
                logger.warning(
                    f"FUZZY MATCH (last resort): '{external_name}' -> '{self.teams[team_id].name}' "
                    f"(confidence={confidence:.2f})"
                )
                return (self.teams[team_id], confidence, False)
        
        # No good match
        logger.warning(f"No match found for '{external_name}' (confidence < {min_confidence})")
        return (None, 0.0, False)
    
    def map_and_save(
        self,
        external_name: str,
        external_id: str,
        min_confidence: float = 0.98,
        dry_run: bool = False,
        allow_non_d1: bool = True,
    ) -> Optional[TeamExternalId]:
        """
        Find team and save TeamExternalId mapping
        
        Args:
            external_name: Team name from source
            external_id: Team ID from source
            min_confidence: Minimum confidence threshold
            dry_run: If True, don't save to DB
            allow_non_d1: If True, create non-D1 teams for NCAA source when not in D1 list
        
        Returns:
            TeamExternalId object or None if no match
        """
        team, confidence, is_override = self.find_team(
            external_name, external_id, min_confidence
        )
        
        if team is None:
            # For NCAA source, create non-D1 team if allowed
            if self.source == 'ncaa' and allow_non_d1 and not dry_run:
                logger.info(f"Creating non-D1 team for '{external_name}'")
                from core.models import Team
                team, created = Team.objects.get_or_create(
                    name=external_name,
                    defaults={'is_d1': False}
                )
                if created:
                    logger.info(f"Created non-D1 team: {external_name}")
                confidence = 1.0
                is_override = False
            else:
                # Track unmatched
                self.unmatched.append({
                    'external_id': external_id,
                    'external_name': external_name,
                })
                return None
        
        if dry_run:
            logger.info(
                f"[DRY RUN] Would map {external_name} -> {team.name} "
                f"(confidence={confidence:.2f}, override={is_override})"
            )
            return None
        
        # Create or update mapping
        mapping, created = TeamExternalId.objects.update_or_create(
            team=team,
            source=self.source,
            defaults={
                'external_id': external_id,
                'external_name': external_name,
                'confidence': confidence,
                'is_manual_override': is_override,
            }
        )
        
        action = "Created" if created else "Updated"
        logger.info(
            f"{action} mapping: {external_name} -> {team.name} "
            f"(confidence={confidence:.2f}, override={is_override}, is_d1={team.is_d1})"
        )
        
        return mapping
    
    def bulk_map(
        self,
        teams_data: List[Dict[str, str]],
        min_confidence: float = 0.98,
        dry_run: bool = False,
    ) -> Dict[str, any]:
        """
        Map multiple teams at once
        
        Args:
            teams_data: List of dicts with 'external_id' and 'external_name'
            min_confidence: Minimum confidence threshold
            dry_run: If True, don't save to DB
        
        Returns:
            Summary dict with stats
        """
        results = {
            'total': len(teams_data),
            'mapped': 0,
            'unmatched': 0,
            'unmatched_teams': [],
        }
        
        with transaction.atomic():
            for team_data in teams_data:
                mapping = self.map_and_save(
                    external_name=team_data['external_name'],
                    external_id=team_data['external_id'],
                    min_confidence=min_confidence,
                    dry_run=dry_run,
                )
                
                if mapping:
                    results['mapped'] += 1
                else:
                    results['unmatched'] += 1
                    results['unmatched_teams'].append(team_data)
        
        logger.info(
            f"Bulk mapping complete: {results['mapped']} mapped, "
            f"{results['unmatched']} unmatched"
        )
        
        return results
    
    def get_team_by_external_id(self, external_id: str) -> Optional[Team]:
        """
        Retrieve Team from cached TeamExternalId mapping
        
        Args:
            external_id: External source ID
        
        Returns:
            Team object or None
        """
        try:
            mapping = TeamExternalId.objects.select_related('team').get(
                source=self.source,
                external_id=external_id
            )
            return mapping.team
        except TeamExternalId.DoesNotExist:
            return None
    
    def export_unmatched(self, output_file: str):
        """
        Export unmatched teams to CSV/JSON for manual review
        
        Args:
            output_file: Path to output file (.csv or .json)
        """
        import json
        import csv
        
        output_path = Path(output_file)
        
        if output_path.suffix == '.json':
            with open(output_path, 'w') as f:
                json.dump(self.unmatched, f, indent=2)
        elif output_path.suffix == '.csv':
            with open(output_path, 'w', newline='') as f:
                if self.unmatched:
                    writer = csv.DictWriter(f, fieldnames=self.unmatched[0].keys())
                    writer.writeheader()
                    writer.writerows(self.unmatched)
        else:
            raise ValueError("Output file must be .csv or .json")
        
        logger.info(f"Exported {len(self.unmatched)} unmatched teams to {output_path}")


def get_or_create_mapper(source: str) -> TeamMapper:
    """
    Factory function to get a TeamMapper instance
    
    Args:
        source: Data source ('ncaa', 'espn', etc.)
    
    Returns:
        TeamMapper instance
    """
    return TeamMapper(source=source)
