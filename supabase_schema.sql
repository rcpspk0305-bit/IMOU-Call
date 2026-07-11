-- SQL Schema Setup for Imou-Exotel-Telegram Monitoring Application

-- Create the system_state table
CREATE TABLE IF NOT EXISTS system_state (
    id SERIAL PRIMARY KEY,
    is_paused BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Seed initial state row if it does not exist
INSERT INTO system_state (id, is_paused) 
VALUES (1, FALSE) 
ON CONFLICT (id) DO NOTHING;

-- Create the camera_logs table to capture offline alert records
CREATE TABLE IF NOT EXISTS camera_logs (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    device_id VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    notification_sent BOOLEAN DEFAULT TRUE
);

-- Create the system_session table to track active web session heartbeats
CREATE TABLE IF NOT EXISTS system_session (
    id VARCHAR(255) PRIMARY KEY,
    last_active_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Seed initial session row if it does not exist
INSERT INTO system_session (id, last_active_at)
VALUES ('00000000-0000-0000-0000-000000000001', NOW())
ON CONFLICT (id) DO NOTHING;

