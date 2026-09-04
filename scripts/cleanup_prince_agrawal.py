#!/usr/bin/env python3
"""
Delete submission data for Prince Agrawal to allow re-testing.
This script removes: pc_submissions, pc_responses, pc_evaluation_jobs, and resets pc_participants status.
"""

import os
import sys

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from supabase import create_client, Client

# Supabase credentials
SUPABASE_URL = "https://yvvjfvdpbhktmsqfordh.supabase.co"
SUPABASE_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inl2dmpmdmRwYmhrdG1zcWZvcmRoIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NzE1MzkxOSwiZXhwIjoyMTAyNzI5OTE5fQ.RDRMOG3zFmV4PoBi98vF624esf-jiG4nE_gnQDO2s2k"

def delete_prince_agrawal_data():
    """Find and delete Prince Agrawal's submission data."""

    # Initialize Supabase client with service role key
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    print("Searching for Prince Agrawal in pc_participants...")

    # First, find the participant - search by display_name or find all and filter
    # Since we don't know the exact name, let's search for any participant with 'prince' or 'agrawal'
    response = supabase.table('pc_participants').select('*').execute()

    prince_participant = None
    for p in response.data:
        display_name = p.get('display_name', '').lower()
        email = p.get('email', '').lower()
        if 'prince' in display_name or 'prince' in email or 'agrawal' in display_name or 'agrawal' in email:
            prince_participant = p
            break

    if not prince_participant:
        print("❌ Prince Agrawal not found in pc_participants")
        print("\nAll participants:")
        for p in response.data:
            print(f"  - ID: {p['id']}, Name: {p.get('display_name')}, Email: {p.get('email')}")
        return

    print(f"\n✅ Found participant:")
    print(f"   ID: {prince_participant['id']}")
    print(f"   Name: {prince_participant.get('display_name')}")
    print(f"   Email: {prince_participant.get('email')}")
    print(f"   Competition ID: {prince_participant.get('competition_id')}")
    print(f"   Status: {prince_participant.get('status')}")

    participant_id = prince_participant['id']
    competition_id = prince_participant.get('competition_id')

    # Find their submission
    print("\nSearching for submissions...")
    sub_response = supabase.table('pc_submissions').select('*').eq('participant_id', participant_id).execute()

    if not sub_response.data:
        print("No submissions found for this participant.")
    else:
        submission_ids = [s['id'] for s in sub_response.data]
        print(f"Found {len(submission_ids)} submission(s): {submission_ids}")

        # Delete evaluation jobs for these submissions
        if submission_ids:
            print("\nDeleting evaluation jobs...")
            for sub_id in submission_ids:
                # Find responses first
                resp_response = supabase.table('pc_responses').select('id').eq('submission_id', sub_id).execute()
                response_ids = [r['id'] for r in resp_response.data]

                if response_ids:
                    print(f"  Deleting {len(response_ids)} evaluation jobs for submission {sub_id}...")
                    for resp_id in response_ids:
                        supabase.table('pc_evaluation_jobs').delete().eq('response_id', resp_id).execute()

                    # Delete responses
                    print(f"  Deleting {len(response_ids)} responses...")
                    supabase.table('pc_responses').delete().eq('submission_id', sub_id).execute()

            # Delete submissions
            print(f"Deleting {len(submission_ids)} submission(s)...")
            for sub_id in submission_ids:
                supabase.table('pc_submissions').delete().eq('id', sub_id).execute()

    # Reset participant status
    print("\nResetting participant status to 'REGISTERED'...")
    supabase.table('pc_participants').update({
        'status': 'REGISTERED',
        'submitted_at': None
    }).eq('id', participant_id).execute()

    print("\n✅ Cleanup complete! Prince Agrawal can now re-test the system.")

if __name__ == "__main__":
    print("=" * 60)
    print("PRINCE AGRAWAL SUBMISSION DATA CLEANUP")
    print("=" * 60)
    delete_prince_agrawal_data()
    print("\nDone.")
