# 🤖 AI INTERVIEWER — Smart Malpractice Detection System  
### Flask + FastAPI + OpenCV + Audio + Report Generation  

---

## 🧠 Overview
The **AI Interviewer** is an intelligent virtual interviewing and proctoring platform that ensures fairness and authenticity during online interviews.  
It uses **real-time face, voice, and activity monitoring** to detect any malpractice or suspicious behavior during a session.  

This project integrates a **Flask frontend** for real-time interaction and a **FastAPI backend** for secure API management.

---

## 🚀 Features

### 🎥 Vision-Based Detection
- **Face Registration** – Capture and register user face before the interview.  
- **Intruder Detection** – Detects multiple faces in the frame.  
- **Looking-Away Detection** – Monitors if the candidate is looking away from the screen.  
- **Out-of-Frame Detection** – Detects when the candidate leaves the camera frame.  
- **Gadget Detection** – Identifies devices like mobile phones or laptops.  
- **Auto Warning System** – 3 warnings before termination.  
- **Session Termination** – Ends the interview automatically on 4th violation.  

### 🎧 Audio & Activity Monitoring
- **Voice Registration** – Stores user’s baseline voice sample.  
- **Voice Mismatch Detection** – Detects unregistered or background voices.  
- **Extra Noise Alert** – Monitors suspicious background sounds.  
- **Website/App Switching Detection** – Detects when candidate switches away from the interview tab.  

### 🧾 Logging & Reports
- **System Log Panel** – Records all events with timestamps.  
- **Auto PDF Report Generation** – Generates a summary report after each session.  
- **Transcript Storage** – Saves all spoken or typed responses.  

### 🧩 System Interface
- **Flask Frontend (UI)** – Real-time camera preview and status display.  
- **FastAPI Backend** – REST API for managing logs, violations, and reports.  

---

## 🧱 Project Structure

- Ready-to-run (full features)

Instructions:
1. Unzip this folder to ~/Downloads or your preferred location.
2. cd 
3. python3.12 -m venv venv   # recommended; or python3 -m venv venv
4. source venv/bin/activate
5. pip install --upgrade pip setuptools wheel
6. pip install -r requirements.txt
   - Note: librosa and numba may require Python <= 3.13; if you run into installation errors, use Python 3.12.
7. python app.py
8. Open http://127.0.0.1:5050 in Chrome and allow camera & mic.
