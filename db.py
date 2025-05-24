from datetime import datetime

def log_signal(user_id: str, input_data: dict, output_data: dict):
    # Replace this with actual DB insert (MongoDB, Supabase, etc.)
    print("[LOGGED SIGNAL]")
    print("User:", user_id)
    print("Input:", input_data)
    print("Output:", output_data)
    print("Time:", datetime.utcnow().isoformat())