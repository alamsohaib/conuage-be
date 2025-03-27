-- Create the pgvector extension if it doesn't exist
CREATE EXTENSION IF NOT EXISTS vector;

-- Create document_embeddings table
CREATE TABLE document_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    location_id UUID NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536) NOT NULL, -- OpenAI embeddings are 1536 dimensions
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id, page_number)  -- Changed unique constraint to only document_id and page_number
);

-- Create function to insert or update document embedding
CREATE OR REPLACE FUNCTION upsert_document_embedding(
    p_document_id UUID,
    p_location_id UUID,
    p_page_number INTEGER,
    p_content TEXT,
    p_embedding FLOAT[],
    p_created_at TIMESTAMP WITH TIME ZONE,
    p_updated_at TIMESTAMP WITH TIME ZONE
) RETURNS SETOF document_embeddings AS $$
BEGIN
    RETURN QUERY
    INSERT INTO document_embeddings (
        document_id,
        location_id,
        page_number,
        content,
        embedding,
        created_at,
        updated_at
    ) VALUES (
        p_document_id,
        p_location_id,
        p_page_number,
        p_content,
        p_embedding::vector,
        p_created_at,
        p_updated_at
    )
    ON CONFLICT (document_id, page_number) 
    DO UPDATE SET
        content = EXCLUDED.content,
        embedding = EXCLUDED.embedding,
        location_id = EXCLUDED.location_id,
        updated_at = EXCLUDED.updated_at
    RETURNING *;
END;
$$ LANGUAGE plpgsql;
