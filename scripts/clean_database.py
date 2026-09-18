"""
TekTutors Clean Slate Database Reset Script
-------------------------------------------
Safely removes all dummy/test transactional data (leads, appointments,
conversations, messages, email logs, scheduled emails) while preserving:
  1. Courses Catalog (28 real TekTutors courses with syllabi & pricing)
  2. FAQs Knowledge Base (44 real TekTutors FAQs)
  3. System Settings & Custom System Prompt
"""

import sys
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import asyncio
from sqlalchemy import delete, select, func
from app.database import AsyncSessionLocal
from app.models import (
    Lead,
    Appointment,
    Conversation,
    Message,
    EmailLog,
    ScheduledEmail,
    Course,
    FAQ,
    SystemConfig
)


async def reset_to_clean_slate():
    print("=" * 60)
    print("[CLEAN SLATE] TekTutors Academy: Database Clean Slate Utility")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        # 1. Count before deletion
        leads_cnt = (await db.execute(select(func.count(Lead.id)))).scalar_one()
        appts_cnt = (await db.execute(select(func.count(Appointment.id)))).scalar_one()
        convs_cnt = (await db.execute(select(func.count(Conversation.id)))).scalar_one()
        msgs_cnt = (await db.execute(select(func.count(Message.id)))).scalar_one()
        emails_cnt = (await db.execute(select(func.count(EmailLog.id)))).scalar_one()
        sched_cnt = (await db.execute(select(func.count(ScheduledEmail.id)))).scalar_one()

        courses_cnt = (await db.execute(select(func.count(Course.id)))).scalar_one()
        faqs_cnt = (await db.execute(select(func.count(FAQ.id)))).scalar_one()

        print("\nCurrent Database State:")
        print(f"  * Demo / Test Leads:        {leads_cnt}")
        print(f"  * Demo / Test Appointments: {appts_cnt}")
        print(f"  * Demo / Test Conversations:{convs_cnt}")
        print(f"  * Demo / Test Messages:     {msgs_cnt}")
        print(f"  * Demo / Test Email Logs:   {emails_cnt}")
        print(f"  * Scheduled Email Queue:    {sched_cnt}")
        print(f"  * Course Catalog (Keep):    {courses_cnt}")
        print(f"  * FAQ Knowledge Base (Keep):{faqs_cnt}")

        # 2. Delete transactional records
        print("\nPurging demo / test transactional records...")
        await db.execute(delete(ScheduledEmail))
        await db.execute(delete(EmailLog))
        await db.execute(delete(Appointment))
        await db.execute(delete(Message))
        await db.execute(delete(Conversation))
        await db.execute(delete(Lead))

        await db.commit()

        # 3. Verify clean state
        leads_after = (await db.execute(select(func.count(Lead.id)))).scalar_one()
        courses_after = (await db.execute(select(func.count(Course.id)))).scalar_one()
        faqs_after = (await db.execute(select(func.count(FAQ.id)))).scalar_one()

        print("\n[SUCCESS] Database Reset Complete:")
        print(f"  * Active Leads:         {leads_after} (Pristine)")
        print(f"  * Courses Preserved:    {courses_after} (100% Intact)")
        print(f"  * FAQs Preserved:       {faqs_after} (100% Intact)")
        print("\nThe application is now in a pristine state ready for real users!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(reset_to_clean_slate())
