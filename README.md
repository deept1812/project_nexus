# 🚀 Project Nexus – Autonomous AI Logistics & Supply Chain Platform

🔗 **Live Demo:** [YOUR_RENDER_LINK_HERE]([YOUR_RENDER_LINK_HERE](https://project-nexus-0zk6.onrender.com/))

**Project Nexus** is a full-stack, multi-portal logistics management platform that tracks the end-to-end lifecycle of an order—from warehouse intake and courier dispatch to live customer tracking and AI-powered support.

---

## ✨ Key Features

- **Passwordless Customer OTP Login:** Integrated **Phone.email API** for SMS/WhatsApp OTP authentication with backend session validation.
- **Strict Role-Based Access Control (RBAC):** Route-level security guards isolating **Customer**, **Warehouse WMS**, **Delivery Partner**, and **Admin** portals.
- **Customer Data Isolation:** Parameterized SQLAlchemy queries ensuring customers only view orders linked to their verified phone number or email.
- **Embedded Groq AI Support Assistant:** Context-aware floating chatbot drawer inside the customer dashboard for live order tracking and automated ticket escalation.
- **Mobile-Responsive UI:** Adaptive Bootstrap 5 layouts across smartphones, tablets, and desktops.

---

## 🔑 Demo Credentials (For Testing)

| Portal | Route | Login Method / Username | Password |
| :--- | :--- | :--- | :--- |
| **Customer Portal** | `/customer` | **Phone.email OTP** (SMS / WhatsApp) | *No password (OTP verified)* |
| **Warehouse WMS** | `/warehouse` | `warehouse1` | `wh123` |
| **Delivery Partner** | `/delivery` | `delivery1` | `del123` |
| **Admin Dashboard** | `/admin` | `admin` | `admin123` |

---

## 🛠️ Tech Stack

- **Backend:** Python, Flask, SQLAlchemy
- **Database:** PostgreSQL (Hosted on Render)
- **AI & Auth Integrations:** Groq LLM API, Phone.email OTP API
- **Frontend:** HTML5, CSS3, JavaScript (ES6+), Bootstrap 5
