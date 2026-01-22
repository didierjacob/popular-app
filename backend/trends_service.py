"""
Google Trends Service
Fetches trending personalities from Google Trends and updates the database
"""

from pytrends.request import TrendReq
from datetime import datetime, timedelta
import logging
import re

logger = logging.getLogger(__name__)

# Common patterns to identify person names vs topics/events
PERSON_INDICATORS = [
    # Titles
    r'\b(Mr|Mrs|Ms|Dr|Prof|President|Prime Minister|King|Queen|Prince|Princess)\b',
    # Common name patterns (capitalized words)
    r'^[A-Z][a-z]+\s+[A-Z][a-z]+',
    # Avoid common non-person terms
]

NON_PERSON_KEYWORDS = [
    'weather', 'election', 'game', 'movie', 'series', 'show', 'concert',
    'festival', 'championship', 'cup', 'olympics', 'news', 'update',
    'covid', 'virus', 'storm', 'hurricane', 'earthquake', 'war',
    'stock', 'market', 'price', 'app', 'iphone', 'samsung', 'vs',
    'how to', 'what is', 'where', 'when', 'why', 'match', 'live',
]


class GoogleTrendsService:
    def __init__(self):
        """Initialize pytrends with global settings"""
        self.pytrends = TrendReq(hl='en-US', tz=0)
    
    def is_likely_person_name(self, term: str) -> bool:
        """
        Heuristic to determine if a search term is likely a person's name
        """
        term_lower = term.lower()
        
        # Exclude non-person keywords
        for keyword in NON_PERSON_KEYWORDS:
            if keyword in term_lower:
                return False
        
        # Check if it contains numbers (less likely to be a person)
        if any(char.isdigit() for char in term):
            return False
        
        # Check if it has at least 2 words (First Last name pattern)
        words = term.split()
        if len(words) < 2:
            return False
        
        # Check if words are capitalized (proper nouns)
        if not all(word[0].isupper() for word in words if word):
            return False
        
        return True
    
    def fetch_trending_searches(self, limit=50):
        """
        Fetch trending searches from Google Trends
        Returns a list of trending terms
        """
        try:
            # Get trending searches (global)
            trending_searches_df = self.pytrends.trending_searches(pn='united_states')
            
            if trending_searches_df is not None and not trending_searches_df.empty:
                # Get top N trending searches
                trending_list = trending_searches_df[0].head(limit).tolist()
                logger.info(f"Fetched {len(trending_list)} trending searches")
                return trending_list
            else:
                logger.warning("No trending searches found")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching trending searches: {e}")
            return []
    
    def filter_personalities(self, trending_list):
        """
        Filter trending searches to keep only likely person names
        """
        personalities = []
        
        for term in trending_list:
            if self.is_likely_person_name(term):
                personalities.append(term)
                logger.info(f"Identified as person: {term}")
            else:
                logger.debug(f"Filtered out non-person: {term}")
        
        return personalities
    
    def get_trending_personalities(self, limit=20):
        """
        Main method to get trending personalities
        Returns a list of person names that are trending
        """
        try:
            # Fetch trending searches
            trending_searches = self.fetch_trending_searches(limit=50)
            
            if not trending_searches:
                return []
            
            # Filter to keep only personalities
            personalities = self.filter_personalities(trending_searches)
            
            # Return top N
            return personalities[:limit]
            
        except Exception as e:
            logger.error(f"Error getting trending personalities: {e}")
            return []


# Singleton instance
trends_service = GoogleTrendsService()
