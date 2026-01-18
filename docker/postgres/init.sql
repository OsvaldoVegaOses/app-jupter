-- PostgreSQL initialization script
-- This script runs once when the container is first created

-- Enable fuzzystrmatch extension for Levenshtein distance
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;

-- Enable pg_trgm extension for trigram similarity (bonus)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Verify extensions are installed
SELECT extname FROM pg_extension WHERE extname IN ('fuzzystrmatch', 'pg_trgm');
