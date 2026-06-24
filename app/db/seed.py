import uuid
from sqlalchemy.orm import Session
from app.core.database import SessionLocal, engine, Base
from app.models.service import Service
from app.models.investigation import Investigation
from app.repositories.investigation_repository import InvestigationRepository
from app.schemas.investigation import InvestigationCreate

# Import all models to ensure metadata matches
import app.db.base # noqa

def seed_db():
    db = SessionLocal()
    try:
        # Create all tables if they don't exist
        print("Ensuring tables are initialized...")
        Base.metadata.create_all(bind=engine)
        
        # Check if database has services already
        if db.query(Service).count() > 0:
            print("Services already seeded. Skipping...")
            return

        print("Seeding services...")
        services_data = [
            {
                "name": "checkout-api",
                "description": "Orchestrates cart items, discounts, and customer checkout flows.",
                "environment": "production",
                "owner": "Checkout Squad",
                "status": "degraded"
            },
            {
                "name": "payment-api",
                "description": "Secure billing interface integrating with external Stripe gateway API.",
                "environment": "production",
                "owner": "FinTech Squad",
                "status": "operational"
            },
            {
                "name": "inventory-api",
                "description": "Manages catalog stocks, warehouse locations, and reservations.",
                "environment": "production",
                "owner": "Logistics Squad",
                "status": "operational"
            },
            {
                "name": "user-api",
                "description": "Authenticates tokens and retrieves customer profiles.",
                "environment": "production",
                "owner": "Identity Squad",
                "status": "operational"
            }
        ]

        seeded_services = {}
        for s_data in services_data:
            service = Service(**s_data)
            db.add(service)
            db.commit()
            db.refresh(service)
            seeded_services[service.name] = service
            print(f"Created Service: {service.name} ({service.id})")

        print("Seeding investigations...")
        investigations_data = [
            {
                "title": "Spike in checkout payment latency",
                "question": "Why did checkout checkout-api calls payment-api start timing out around 14:00 today?",
                "service_name": "checkout-api"
            },
            {
                "title": "Postgres connection pool exhausted",
                "question": "What is causing pg connection timeouts and spikes in CPU on checkout-api?",
                "service_name": "checkout-api"
            },
            {
                "title": "Memory leak OOM loop in inventory-api",
                "question": "Why did inventory-api start crashing with OOMKilled code 137?",
                "service_name": "inventory-api"
            }
        ]

        for inv in investigations_data:
            service = seeded_services.get(inv["service_name"])
            if not service:
                continue

            inv_in = InvestigationCreate(
                title=inv["title"],
                question=inv["question"],
                service_id=service.id
            )
            
            created_inv = InvestigationRepository.create(db, inv_in)
            print(f"Created Investigation: '{created_inv.title}' on service {inv['service_name']} with generated RCA.")

        print("Seeding complete successfully!")

    except Exception as e:
        print(f"Error during seeding: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_db()
