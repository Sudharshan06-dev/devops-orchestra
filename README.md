# 🧠 DevOps Orchestra – Intelligent DevOps Assistant Platform

DevOps Orchestra is an AI-powered, intent-driven platform that transforms how developers deploy and monitor cloud infrastructure. Instead of writing Terraform scripts, configuring AWS resources, or checking logs across platforms, users simply describe their needs in **natural language** — and the system handles the rest.

## 🔍 What It Does

✔️ Deploy cloud-native infrastructure using natural language prompts  
✔️ Integrate with **OpenAI/Claude** to generate Terraform from intent  
✔️ Deploy applications to **AWS ECS with Fargate**, **RDS**, and more  
✔️ Centralized dashboard to **track and monitor services**  
✔️ Log-based root cause analysis using **LGTM (Loki, Grafana, Tempo, Mimir)**  
✔️ Google SSO with **AWS Cognito** for secure login  
✔️ Fully containerized backend with **FastAPI** and **Spring Boot** microservices  
✔️ Event-driven using **Kafka** for real-time orchestration  

---

## 🧱 Architecture Overview

<img width="3261" height="1641" alt="image" src="https://github.com/user-attachments/assets/06037bb5-ea62-4a7e-99b7-1e2ee44b8bd4" />

<!-- Replace the path with your actual diagram once added to repo -->

### Core Services

| Service | Technology | Description |
|--------|------------|-------------|
| Frontend | Angular + RxJS | Chat UI, login, dashboard, Grafana logs |
| Intent Service | FastAPI | Classifies user request, routes to correct agent |
| Infra Generator | Spring Boot | Converts prompt → Terraform config |
| Event Streamer | Kafka | Dispatches deploy events, logs, metrics |
| Observability | LGTM Stack | Aggregates ECS/Lambda logs and shows in Grafana |
| Auth | AWS Cognito | Google SSO authentication |
| Infra Target | ECS + RDS + S3 | Terraform-deployed AWS services |
| Log Forwarding | Fluent Bit / Lambda | Pushes CloudWatch logs to local Loki |

---

## 🔐 Authentication (Cognito)

- Uses **AWS Cognito User Pool**
- Google login enabled via SSO federation
- Auth flow redirects user to Cognito Hosted UI
- JWT is returned on successful login and stored for session use

---

## 💬 Prompt Examples

```text
"Deploy a Python app with MySQL and autoscaling"
→ Terraform creates ECS Fargate, ALB, and RDS

"Add Redis cache to my app"
→ Modifies existing TF state to include ElastiCache

"Why is my app crashing?"
→ Pulls logs from Loki and summarizes RCA
```

---

## 📦 Tech Stack

- **Frontend:** Angular 17, RxJS, Chart.js 
- **Backend:** FastAPI, Spring Boot, Kafka  
- **Infra-as-Code:** Terraform  
- **Cloud:** AWS (Cognito, ECS, EKS, Lambda, S3, RDS, CloudWatch, IAM)  
- **Logs & Monitoring:** Loki, Grafana, Tempo, Mimir  
- **Agents:** OpenAI / Claude for NLP + reasoning  

---

## 📌 Getting Started

```bash
# Install frontend dependencies
cd frontend
npm install

# Start frontend
ng serve

# Start FastAPI Intent Service
cd services/intent-service
uvicorn main:app --reload

# Start Spring Boot Infra Generator
cd services/infra-generator
./mvnw spring-boot:run

# Start Kafka & LGTM stack using Docker Compose
docker-compose -f docker-compose.lgtm.yml up
```

---

## 🤝 Contributing

This is a solo academic project submitted as part of a graduate capstone. Contributions and suggestions are welcome — open an issue!

---

## 📄 License

MIT License – feel free to use and adapt this project for learning and portfolio building.

---

## 📷 Demo (Coming Soon)

Screencast or screenshots will be added once the first prototype is ready.
