-- Drop existing policy if it exists
DROP POLICY IF EXISTS "Service role can update documents" ON documents;

-- Create policy for service role to update documents
CREATE POLICY "Service role can update documents" 
ON documents FOR UPDATE 
TO service_role 
USING (true) 
WITH CHECK (true);
