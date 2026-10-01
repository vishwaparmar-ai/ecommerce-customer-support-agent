# ShopFlow AI — Production Customer Support Agent

> A production-oriented AI customer support agent for an e-commerce platform, combining **LLM-powered conversation**, **RAG-based policy knowledge**, **live PostgreSQL business data**, **typed business tools**, **human approval**, and **human escalation**.

---

## Overview

ShopFlow AI is a fictional e-commerce customer support platform where customers can interact with an AI assistant to get help with orders, shipments, returns, refunds, cancellations, and company policies.

Instead of relying only on an LLM's knowledge, the agent connects to deterministic backend services and controlled business tools.

For example, when a customer asks:

> **"What is the status of my order?"**

the AI agent can:

1. Identify the customer's intent.
2. Authenticate the customer.
3. Retrieve the customer's order.
4. Check shipment information.
5. Validate the retrieved information.
6. Generate a grounded response.
7. Return structured order/shipment information to the customer.

The AI agent acts primarily as an **orchestration layer**. Business rules and transactional operations remain inside deterministic backend services.

---

## Key Features

### 🤖 AI Customer Support

The customer can ask natural-language questions such as:

* "Where is my order?"
* "What is the status of my latest order?"
* "Can I return this product?"
* "How long do refunds take?"
* "Can I cancel my order?"
* "What is your return policy?"

The agent determines the appropriate workflow and uses the required knowledge source or business tool.

---

### 📦 Live Order Information

For transactional questions, the system retrieves information from PostgreSQL through controlled backend tools.

Examples:

* Customer profile
* Orders
* Order items
* Shipment status
* Payment status
* Return status
* Refund status

The LLM does **not** directly query the database.

---

### 📚 RAG-Based Policy Knowledge

Policy and support documentation is indexed using a RAG pipeline.

Knowledge sources include:

* Return policy
* Refund policy
* Shipping policy
* Cancellation policy
* Warranty policy
* Payment policy
* Delivery exceptions
* Customer service SOP
* FAQ

The RAG pipeline follows:

```text
Documents
    ↓
Parsing
    ↓
Cleaning
    ↓
Metadata Extraction
    ↓
Chunking
    ↓
Embeddings
    ↓
pgvector
    ↓
Retrieval
    ↓
Optional Reranking
    ↓
Context
    ↓
LLM
```

RAG is used for **policies and knowledge**, while PostgreSQL and business tools are used for **live transactional information**.

---

### 🔧 Controlled AI Tools

The agent can use allowlisted, typed tools such as:

```text
search_knowledge_base
get_customer_profile
get_order
list_orders
track_shipment
get_payment_status
check_return_eligibility
create_return_request
get_refund_status
create_refund
cancel_order
create_support_ticket
escalate_to_human
```

Tool arguments are validated before execution.

Identity is derived from the authenticated customer context rather than allowing the LLM to provide arbitrary customer IDs.

---

### 🔐 Authentication & Authorization

The platform includes:

* JWT authentication
* Password hashing
* Customer identity validation
* Object-level authorization
* Role separation
* Protection against cross-customer data access

A customer should only be able to access their own orders, payments, shipments, returns, and refunds.

---

### ⚠️ Approval-Gated Actions

Consequential actions are not executed blindly by the AI.

For example:

```text
Customer Request
      ↓
AI determines action
      ↓
Validate eligibility
      ↓
AI proposes action
      ↓
Customer / authorized human approval
      ↓
Deterministic service executes action
      ↓
Audit log
      ↓
AI confirms result
```

This applies to high-impact operations such as refunds or other consequential account actions.

---

### 🧑‍💼 Human Escalation

The system can escalate conversations when the AI cannot safely resolve the request.

Escalation scenarios include:

* Low confidence
* Conflicting information
* Fraud or account-security concerns
* High-value or unusual compensation
* Policy ambiguity
* Repeated failures
* Explicit human-support request
* Consequential tool failure

When escalation is required, the system can create a support ticket and hand the conversation over to human support.

---

### 🧠 Stateful Agent with LangGraph

The support agent is implemented as a stateful workflow.

High-level flow:

```text
START
  ↓
Load Conversation State
  ↓
Classify Intent
  ↓
Route Request
  ├── Knowledge
  ├── Order
  ├── Return
  ├── Refund
  ├── Cancellation
  └── Escalation
          ↓
Response Validator
          ↓
Persist Message + Audit
          ↓
END
```

The agent state can contain:

```text
conversation_id
authenticated_customer_id
recent_messages
conversation_summary
intent
retrieved_context
tool_results
risk
approval
escalation
```

---

## System Architecture

```text
┌──────────────────────────────┐
│        Customer UI           │
│  E-commerce App + AI Chat    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│          FastAPI             │
│     API + Authentication     │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│     Conversation Service     │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│       LangGraph Agent        │
│                              │
│  Intent / Routing            │
│  Knowledge Retrieval         │
│  Business Tools              │
│  Risk / Approval             │
│  Response Validation         │
│  Human Escalation            │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│       Service Layer          │
│    Business Rules / Logic    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│       Repository Layer       │
└──────────────┬───────────────┘
               │
       ┌───────┴────────┐
       ▼                ▼
┌─────────────┐  ┌─────────────┐
│ PostgreSQL  │  │  pgvector   │
│ Business DB │  │ RAG Storage │
└─────────────┘  └─────────────┘
```

The architecture intentionally separates:

* AI orchestration
* Business logic
* Database access
* Knowledge retrieval
* Authentication
* Authorization
* Transaction execution

---

## Customer Experience

ShopFlow AI is designed primarily as a **customer-facing e-commerce application with an embedded AI support assistant**, rather than as a traditional support-ticket dashboard.

A customer can browse the application normally and open the AI assistant whenever help is needed.

### Example

Customer:

> What is the status of my order?

AI:

> Your latest order **#ORD-10482** is currently **In Transit**.

The UI can provide structured actions such as:

```text
[ View Order ]    [ Track Shipment ]
```

The customer can then continue the conversation:

> Where is it right now?

The agent can use the existing conversation context and retrieve the shipment information.

---

## Rich AI Responses

The frontend can render structured business components rather than displaying only plain text.

Possible response components include:

```text
Text Response
Order Card
Shipment Card
Product Card
Return Eligibility Card
Refund Card
Policy Citation
Confirmation Card
Escalation Card
```

This allows the AI assistant to behave more like an integrated product feature instead of a generic chatbot.

---

## Database Model

The platform is designed around the following primary entities:

```text
customers
products
orders
order_items
payments
shipments
returns
refunds
support_tickets
conversations
messages
tool_calls
audit_logs
```

Relationships allow the system to connect customer conversations with their authenticated business data and AI actions.

---

## API

The backend exposes APIs for:

### Authentication

```text
POST /auth/register
POST /auth/login
```

### Products

```text
GET /products
GET /products/{product_id}
```

### Orders

```text
GET /orders
GET /orders/{order_id}
```

### Payment & Shipment

```text
GET /orders/{order_id}/payment
GET /orders/{order_id}/shipment
```

### Returns

```text
GET  /returns
POST /returns
```

### Refunds

```text
GET /refunds
POST /refunds
```

### Support Tickets

```text
GET  /support/tickets
POST /support/tickets
```

### Conversations

```text
POST /conversations
GET  /conversations/{conversation_id}
POST /conversations/{conversation_id}/messages
```

### Health

```text
GET /health
```

---

## Technology Stack

| Layer           | Technology                                               |
| --------------- | -------------------------------------------------------- |
| Language        | Python 3.11                                              |
| Backend         | FastAPI                                                  |
| Validation      | Pydantic v2                                              |
| ORM             | SQLAlchemy 2.x                                           |
| Database        | PostgreSQL                                               |
| Migrations      | Alembic                                                  |
| Authentication  | JWT + Password Hashing                                   |
| Agent Framework | LangGraph                                                |
| LLM Integration | LangChain                                                |
| RAG             | LangChain + pgvector                                     |
| Vector Database | PostgreSQL + pgvector                                    |
| Frontend        | Streamlit / Customer UI                                  |
| Testing         | pytest + httpx                                           |
| Code Quality    | Ruff + mypy                                              |
| Containers      | Docker + Docker Compose                                  |
| CI/CD           | GitHub Actions                                           |
| Observability   | Structured logging, tracing, latency/token/cost tracking |

---

## Project Structure

A recommended structure for the implementation is:

```text
shopflow-ai/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py
│   │   │   ├── orders.py
│   │   │   ├── products.py
│   │   │   ├── returns.py
│   │   │   ├── refunds.py
│   │   │   ├── support.py
│   │   │   └── conversations.py
│   │   │
│   │   ├── agent/
│   │   │   ├── graph.py
│   │   │   ├── state.py
│   │   │   ├── nodes/
│   │   │   └── tools/
│   │   │
│   │   ├── auth/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── repositories/
│   │   ├── rag/
│   │   ├── database/
│   │   ├── observability/
│   │   └── main.py
│   │
│   ├── alembic/
│   └── tests/
│
├── frontend/
│   └── ...
│
├── data/
│   └── policies/
│
├── evals/
│   ├── dataset/
│   ├── metrics/
│   └── runners/
│
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── README.md
```

---

# AI Agent Design

## Intent Classification

The agent first determines what the customer is trying to accomplish.

Example intents:

```text
POLICY
ORDER
SHIPMENT
RETURN
REFUND
CANCELLATION
PAYMENT
ESCALATION
UNKNOWN
```

The intent determines which workflow and tools should be used.

---

## Knowledge Requests

Example:

> What is your return policy?

Flow:

```text
User
 ↓
Intent Classification
 ↓
Knowledge Retrieval
 ↓
pgvector
 ↓
Relevant Policy Chunks
 ↓
LLM
 ↓
Validated Response
 ↓
Customer
```

---

## Order Requests

Example:

> Where is my order?

Flow:

```text
User
 ↓
Authentication
 ↓
Intent Classification
 ↓
get_order()
 ↓
track_shipment()
 ↓
Response Validation
 ↓
Structured Response
 ↓
Customer
```

The order information comes from the live application database rather than from RAG.

---

## Return Requests

Example:

> Can I return my headphones?

Flow:

```text
Customer Request
       ↓
Identify Order
       ↓
Check Ownership
       ↓
Check Delivery Status
       ↓
Check Return Window
       ↓
Check Product Eligibility
       ↓
Return Eligibility
       ↓
Create Return Request
```

Business rules are handled by deterministic services rather than being left entirely to the LLM.

---

## Refund Requests

Example:

> Where is my refund?

The agent can:

```text
Retrieve return
      ↓
Check payment
      ↓
Check refund status
      ↓
Validate information
      ↓
Explain refund status
```

For refund creation or other consequential actions, an approval step can be required.

---

# Security

Security is a core part of the architecture.

The system is designed to protect against:

* Unauthorized order access
* Cross-customer data access
* Arbitrary tool execution
* Prompt injection
* Unsafe business operations
* Invalid tool arguments
* Unauthorized consequential actions

Important principles:

```text
Authenticated Identity
        ↓
Object-Level Authorization
        ↓
Allowlisted Tools
        ↓
Typed Arguments
        ↓
Deterministic Business Rules
        ↓
Audit Logging
```

The agent should never be trusted as the final authority for sensitive business operations.

---

# Observability

Each agent execution should capture useful operational information such as:

```text
Conversation ID
Run ID
Intent
Model / Provider
Retrieved Document IDs
Retrieval Scores
Tool Calls
Tool Durations
Validation Result
Escalation
Latency
Token Usage
Estimated Cost
Errors
Retries
```

Sensitive information and secrets should not be unnecessarily written to logs.

---

# Evaluation

The project includes an evaluation strategy based on synthetic customer conversations.

Target evaluation dataset:

```text
150–250 synthetic conversations
```

Evaluation areas include:

* Intent accuracy
* Retrieval Recall@K
* Context relevance
* Tool selection accuracy
* Tool argument accuracy
* Task success
* Groundedness
* Policy compliance
* Safety
* Escalation quality
* Latency
* Cost

The project should measure these metrics rather than claiming performance numbers without evidence.

---

# Testing

The system should include tests for:

### Unit Tests

* Business rules
* Services
* Repositories
* Tool validation
* Authorization
* RAG components
* Agent nodes

### API Tests

* Authentication
* Orders
* Returns
* Refunds
* Conversations
* Support tickets

### Agent Tests

* Intent routing
* Tool selection
* Tool arguments
* Response validation
* Escalation
* Approval workflows

### Evaluation Tests

* Retrieval quality
* Grounded responses
* Task completion
* Safety behavior

---

# Example User Journeys

## 1. Policy Question

```text
Customer
   ↓
"What is your return policy?"
   ↓
Policy Intent
   ↓
RAG Retrieval
   ↓
Policy Context
   ↓
LLM
   ↓
Grounded Answer
```

---

## 2. Order Status

```text
Customer
   ↓
"What is the status of my order?"
   ↓
Order Intent
   ↓
get_order()
   ↓
track_shipment()
   ↓
Validate Result
   ↓
Order + Shipment Response
```

---

## 3. Return Request

```text
Customer
   ↓
"I want to return my order."
   ↓
Return Intent
   ↓
Verify Ownership
   ↓
Check Eligibility
   ↓
Approval / Action
   ↓
Create Return
   ↓
Audit
   ↓
Confirmation
```

---

## 4. Human Escalation

```text
Customer
   ↓
AI cannot safely resolve request
   ↓
Escalation
   ↓
Create Support Ticket
   ↓
Human Support
```

---

# License

This project is intended as a portfolio and learning project.

If a specific license is added to the repository, replace this section with the corresponding license information.
