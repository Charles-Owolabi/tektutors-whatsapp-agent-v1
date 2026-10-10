import os
import re
import ssl
import socket
import smtplib
import asyncio
import logging
import datetime
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any, List
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import EmailLog, Lead, ScheduledEmail

logger = logging.getLogger(__name__)

# Pre-built high-converting email campaign templates
PREBUILT_EMAIL_TEMPLATES = [
    # =========================================================================
    # 1. DIRECT CONVERSION & CLOSING TEMPLATES (Urgency, ROI, Checkout)
    # =========================================================================
    {
        "id": "cart_abandonment_recovery",
        "title": "🛒 Incomplete Checkout & Reserved Slot Expiring",
        "category": "conversion",
        "badge": "Cart Recovery",
        "subject": "⏳ Important: Your reserved 1-on-1 mentor slot expires in 24 hours, {{name}}",
        "body": (
            "Hi {{name}},\n\n"
            "Our admissions system flagged that you generated your enrollment link for **{{course}}**, but your private onboarding is still incomplete.\n\n"
            "To maintain our strict standard of **100% private 1-on-1 live mentorship**, our Senior Practitioners are allocated on a strict first-come basis. Your mentor slot has been held for the last 24 hours and is scheduled for release to our waitlist tomorrow morning.\n\n"
            "**Why Learners Lock In Their Slot Today:**\n"
            "• **Flexible Month-to-Month Tuition:** Invest just **₦100,000 / month** as you learn (pause or cancel anytime).\n"
            "• **10% Upfront Prepayment:** Pay just **₦90,000** today (save ₦10,000 immediately).\n"
            "• **3 Capstone Projects:** Built with real enterprise datasets for your resume and LinkedIn.\n\n"
            "Click below to secure your mentor and confirm your weekend onboarding before your reservation expires."
        ),
        "cta_text": "Confirm Your Registration Now",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "career_roi_payback_breakdown",
        "title": "💰 Tuition ROI & 3-Week Payback Math",
        "category": "conversion",
        "badge": "Career ROI",
        "subject": "Is Tech Mentorship Worth It? The Math Behind Your {{course}} Investment",
        "body": (
            "Hi {{name}},\n\n"
            "When considering advancing your skills, the most important question is: *\"What is my real return on investment?\"*\n\n"
            "Here is the transparent math based on hiring benchmarks for TekTutors graduates:\n\n"
            "**The Numbers:**\n"
            "• **Your Tuition Investment:** ₦100,000 / month (or ₦90,000 with our 10% upfront discount).\n"
            "• **Junior to Mid Data Analyst Salary (Nigeria):** ₦350,000 – ₦750,000 / month.\n"
            "• **Global Remote Roles:** $1,500 – $3,000 / month (₦2,250,000+).\n"
            "• **ROI Payback Period:** **Under 3 weeks** of your first month's compensation.\n\n"
            "Crowded courses give you passive videos with a 5% completion rate. TekTutors gives you a dedicated Senior Practitioner who screenshares with you weekly to ensure you master the skills employers pay for.\n\n"
            "Ready to make the smartest investment in your career?"
        ),
        "cta_text": "Enroll with High ROI",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "fast_action_earlybird_rebate",
        "title": "💳 Full Prepayment 10% Cash Rebate (₦90,000)",
        "category": "conversion",
        "badge": "10% Upfront Rebate",
        "subject": "Claim Your ₦10,000 Upfront Savings on {{course}} (Pay Just ₦90,000)",
        "body": (
            "Hi {{name}},\n\n"
            "Looking to maximize your tuition savings while locking in world-class 1-on-1 mentorship?\n\n"
            "While our flexible **₦100,000/month** billing is popular, students who choose full upfront prepayment unlock an immediate **10% tuition rebate**:\n\n"
            "**Tuition Comparison:**\n"
            "• Standard Monthly Billing: ₦100,000 / month\n"
            "• **Your Upfront Full Discount Rate: ₦90,000** (Save ₦10,000 immediately!)\n\n"
            "**Everything Included:**\n"
            "✅ Live private 1-on-1 mentorship sessions (flexible evening & weekend slots).\n"
            "✅ 3 portfolio capstone projects with direct code walkthroughs.\n"
            "✅ CV optimization, LinkedIn makeover, and tech interview coaching.\n\n"
            "Select the 'Full Prepayment' option at checkout to automatically apply your ₦10,000 rebate:"
        ),
        "cta_text": "Claim ₦10,000 Rebate at Checkout",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "checkout_invoice_delivery",
        "title": "🧾 Official Invoice & Registration Checkout",
        "category": "conversion",
        "badge": "Invoice & Checkout",
        "subject": "Your TekTutors Enrollment Invoice & Reserved Slot for {{course}}",
        "body": (
            "Hi {{name}},\n\n"
            "Thank you for taking the step toward accelerating your career with TekTutors! We have generated your official enrollment link for **{{course}}**.\n\n"
            "**Tuition Options Available:**\n"
            "1. **Flexible Month-to-Month Plan:** ₦100,000 / month (pay as you progress, no lock-in contracts).\n"
            "2. **10% Upfront Prepayment:** ₦90,000 (saves ₦10,000 immediately when paying in full).\n\n"
            "**What Is Included in Your Tuition:**\n"
            "• Live 1-on-1 video coaching with an active Senior Practitioner.\n"
            "• Guided walkthroughs on datasets from real tech enterprises.\n"
            "• 3 employer-ready portfolio projects for LinkedIn & GitHub.\n"
            "• Comprehensive CV review & mock technical interview preparation.\n\n"
            "Click below to complete your checkout and claim your onboarding schedule:"
        ),
        "cta_text": "Proceed to Secure Checkout",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "banker_accountant_switch",
        "title": "💼 Career Switch Blueprint for Finance & Ops Pros",
        "category": "conversion",
        "badge": "Career Switch",
        "subject": "How Bankers & Accountants Pivot to ₦600k/mo Data Roles ({{course}})",
        "body": (
            "Hi {{name}},\n\n"
            "Are you currently working in banking, accounting, customer operations, or audit and feeling stuck in routine spreadsheets?\n\n"
            "Here is a secret hiring managers won't tell you: **You already have the hardest skill to teach — business domain knowledge.**\n\n"
            "By pairing your operational intuition with **SQL queries, Power BI dashboards, and automated Python workflows**, you become 5x more valuable than a pure computer science graduate with zero commercial context.\n\n"
            "**How TekTutors Accelerates Your Pivot:**\n"
            "• **Tailored 1-on-1 Mentorship:** Learn at your own pace without feeling embarrassed by technical questions.\n"
            "• **Weekend-Friendly Sessions:** Keep your current job while building your new portfolio.\n"
            "• **Flexible Tuition:** Invest **₦100,000 / month** (or **₦90,000 upfront**, saving ₦10,000).\n\n"
            "Read how other finance professionals transitioned and start your live training this week:"
        ),
        "cta_text": "Start Your Career Pivot",
        "cta_url": "https://tektutors.com.ng/registration"
    },

    # =========================================================================
    # 2. CONSULTATION & ADMISSIONS FOLLOW-UP TEMPLATES
    # =========================================================================
    {
        "id": "advisor_call_followup",
        "title": "📞 1-on-1 Consultation Follow-Up",
        "category": "follow_up",
        "badge": "Admissions Call",
        "subject": "Great connecting with you, {{name}}! Here is your TekTutors next steps guide",
        "body": (
            "Hi {{name}},\n\n"
            "Thank you for connecting with our Admissions team! We are thrilled about your interest in mastering practical skills in **{{course}}**.\n\n"
            "At TekTutors, you won't be lost in crowded lectures. Your training is delivered via **live 1-on-1 industry mentorship** with weekly real-world projects designed for your career portfolio.\n\n"
            "**Your Next Step:**\n"
            "Our team has reserved a private consultation slot for you. If you are ready to lock in your mentor and start learning, you can complete your enrollment directly below.\n\n"
            "Tuition is completely flexible at **₦100,000/month** (month-to-month billing with no long-term contracts), plus an exclusive **10% upfront discount** (₦90,000) if you choose to pay in full."
        ),
        "cta_text": "Complete Your Enrollment",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "consultation_booking_confirmation",
        "title": "📅 1-on-1 Consultation Call Confirmed",
        "category": "follow_up",
        "badge": "Call Scheduled",
        "subject": "Appointment Confirmed: Your TekTutors 1-on-1 Consultation, {{name}}",
        "body": (
            "Hi {{name}},\n\n"
            "Great news! Your 1-on-1 Academic Discovery Call for **{{course}}** has been officially logged with our Admissions team.\n\n"
            "**What to Expect During Your Session:**\n"
            "• **Custom Skill Assessment:** We evaluate your current technical background and target career trajectory.\n"
            "• **Mentor Matching:** How we pair you with a Senior Industry Practitioner suited to your learning goals.\n"
            "• **Portfolio & Capstone Plan:** A walkthrough of the 3 real-world projects you will build.\n"
            "• **Flexible Tuition Setup:** Details on our ₦100,000/month plan and the 10% upfront rebate (₦90,000).\n\n"
            "An advisor will reach out via WhatsApp/Phone prior to your call. If you're ready to secure your mentor right now, you can also complete your registration below."
        ),
        "cta_text": "Complete Enrollment Online",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "post_advisor_call_action_plan",
        "title": "📋 Post-Discovery Call Personalized Action Plan",
        "category": "follow_up",
        "badge": "Action Plan",
        "subject": "Your Personalized {{course}} Learning Roadmap & Mentor Pairing, {{name}}",
        "body": (
            "Hi {{name}},\n\n"
            "It was fantastic speaking with you during your Academic Discovery Call! Based on your goals and background, here is your customized TekTutors action plan:\n\n"
            "**Your Recommended Pathway: {{course}}**\n"
            "• **Target Milestone 1:** Master foundational diagnostics and advanced data manipulation.\n"
            "• **Target Milestone 2:** Build enterprise-grade SQL relational models and interactive Power BI executive dashboards.\n"
            "• **Target Milestone 3:** Complete 3 end-to-end portfolio capstones published directly to GitHub and LinkedIn.\n\n"
            "**Tuition Options Reviewed:**\n"
            "• Month-to-Month Plan: ₦100,000 / month (zero penalties to pause or cancel).\n"
            "• Full Upfront Prepayment: ₦90,000 (10% upfront discount applied).\n\n"
            "Your assigned Senior Mentor has been reserved for the next 48 hours. Confirm your seat to receive your calendar invite and onboarding materials:"
        ),
        "cta_text": "Activate Your Mentorship",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "syllabus_delivery_followup",
        "title": "📚 Syllabus & Learning Roadmap Delivery",
        "category": "follow_up",
        "badge": "Curriculum",
        "subject": "Your Complete Syllabus & Week-by-Week Roadmap ({{course}})",
        "body": (
            "Hi {{name}},\n\n"
            "As requested, here is the official curriculum breakdown for **{{course}}** at TekTutors Academy.\n\n"
            "**What You Will Master:**\n"
            "• **Foundations & Core Workflows:** Industry best practices and practical setup.\n"
            "• **Hands-On Applied Modules:** Real datasets, business problem solving, and live guided code walkthroughs.\n"
            "• **Employer-Ready Portfolio:** 3 capstone projects built to showcase directly on LinkedIn and your resume.\n"
            "• **1-on-1 Industry Mentorship:** Dedicated private sessions with an experienced practitioner.\n\n"
            "Have questions about prerequisites or scheduling? Simply reply to this email or chat with our admissions advisor on WhatsApp anytime."
        ),
        "cta_text": "Enroll in {{course}}",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "zero_coding_transition_blueprint",
        "title": "🔰 Zero-Coding Background Transition Guide",
        "category": "follow_up",
        "badge": "Beginner Friendly",
        "subject": "Zero Coding Experience? Here is how complete beginners thrive in {{course}}",
        "body": (
            "Hi {{name}},\n\n"
            "Over 70% of our most successful graduates started exactly where you are today: **with zero programming background and wondering if they could truly learn tech.**\n\n"
            "Traditional bootcamps fail beginners because you're dumped into 50-person Zoom calls where tutors rush through slides without checking if anyone is keeping up.\n\n"
            "**The TekTutors 1-on-1 Advantage for Beginners:**\n"
            "1. **Step-by-Step Screen Shares:** Your mentor walks you through installation, syntax, and logic line-by-line.\n"
            "2. **Safe Learning Environment:** Ask every \"silly\" question without peer pressure.\n"
            "3. **Practical Problem Solving:** Learn with relatable business cases rather than abstract mathematics.\n"
            "4. **No Financial Risk:** Pay **₦100,000 / month** as you go, or save ₦10,000 with our **₦90,000 upfront discount**.\n\n"
            "You don't need a computer science degree to build high-paying data skills. You just need a patient mentor dedicated to your success."
        ),
        "cta_text": "Start Learning with a Mentor",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "incomplete_application_followup",
        "title": "⏳ Incomplete Registration Check-in",
        "category": "follow_up",
        "badge": "Re-engagement",
        "subject": "Did you leave something behind, {{name}}? Your TekTutors slot is waiting",
        "body": (
            "Hi {{name}},\n\n"
            "We noticed you recently started exploring our **{{course}}** track but haven't finalized your registration yet.\n\n"
            "We understand that making a career move comes with questions. Whether you're wondering about our flexible weekend schedules, beginner prerequisites, or month-to-month tuition (₦100,000/month), we are here to support you.\n\n"
            "Mentors are assigned on a first-come, first-served basis to maintain strict 1-on-1 quality. Secure your onboarding slot today and start learning this week!"
        ),
        "cta_text": "Resume Application",
        "cta_url": "https://tektutors.com.ng/registration"
    },

    # =========================================================================
    # 3. MARKETING & SOCIAL PROOF TEMPLATES
    # =========================================================================
    {
        "id": "new_cohort_launch",
        "title": "🚀 Upcoming Live Cohort Kickoff",
        "category": "marketing",
        "badge": "Cohort Launch",
        "subject": "🚀 New Weekend Cohort Kickoff: {{course}} starts this Monday!",
        "body": (
            "Hi {{name}},\n\n"
            "Big news! Applications are now officially open for our upcoming live cohort in **{{course}}** starting this week!\n\n"
            "**Why Learners Choose TekTutors:**\n"
            "✅ **100% Live 1-on-1 Mentorship:** Direct video coaching and personalized code reviews.\n"
            "✅ **Zero Pre-recorded Fluff:** Learn modern, in-demand tools with practical real-world datasets.\n"
            "✅ **Flexible Month-to-Month Tuition:** Pay ₦100,000/month as you progress.\n"
            "✅ **Career Mentorship:** Resume building, LinkedIn optimization, and portfolio reviews.\n\n"
            "Slots are strictly capped at 15 learners per track to maintain individualized mentor attention."
        ),
        "cta_text": "Reserve Your Cohort Seat",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "capstone_portfolio_blueprint",
        "title": "📊 3 Employer-Ready Capstones Preview",
        "category": "marketing",
        "badge": "Portfolio Showcase",
        "subject": "The 3 Capstone Projects That Get Our {{course}} Graduates Hired",
        "body": (
            "Hi {{name}},\n\n"
            "In tech hiring, recruiters care 10x more about **what you have built** than multiple-choice certificates.\n\n"
            "During your 1-on-1 mentorship in **{{course}}**, you will build and deploy 3 employer-ready capstones:\n\n"
            "**Your Project Portfolio:**\n"
            "• **Project 1: Enterprise Customer Churn Analysis** — End-to-end diagnostic SQL queries and executive KPI metrics.\n"
            "• **Project 2: Commercial Sales & Revenue Intelligence Dashboard** — Interactive Power BI visual model with custom DAX measures.\n"
            "• **Project 3: Predictive Analytics & Automation Pipeline** — Automated data cleaning, exploratory data analysis, and trend forecasting.\n\n"
            "Every project is hosted on GitHub and LinkedIn with your mentor reviewing every commit. Start building your portfolio this week!"
        ),
        "cta_text": "View Capstone Curriculum",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "alumni_success_spotlight",
        "title": "💼 Student Success Spotlight & Hiring Story",
        "category": "marketing",
        "badge": "Success Story",
        "subject": "From Zero Coding to Senior BI Analyst: Meet our graduate David",
        "body": (
            "Hi {{name}},\n\n"
            "Six months ago, David was working a traditional admin job with zero technical background. Today, he is working full-time as a Business Intelligence Specialist.\n\n"
            "*\"The live 1-on-1 mentor format at TekTutors changed everything for me. Whenever I was stuck on SQL queries or DAX calculations, my mentor jumped on a screen-share and walked me through it in minutes.\"*\n\n"
            "Are you ready to write your own career transformation story? Our next live 1-on-1 mentorship cohort is welcoming new students today."
        ),
        "cta_text": "Start Your Tech Journey",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "free_career_masterclass",
        "title": "🎓 VIP Invite: Tech Career Transition Masterclass",
        "category": "marketing",
        "badge": "Live Masterclass",
        "subject": "🎓 Free Masterclass: How Non-Coders Switch into Data & AI in 2026",
        "body": (
            "Hi {{name}},\n\n"
            "You are cordially invited to our exclusive live interactive masterclass: **Breaking into High-Paying Tech Roles Without a CS Degree**.\n\n"
            "**What We Will Cover:**\n"
            "1. The 3 skills hiring managers look for in Data Analysts & Python Practitioners.\n"
            "2. How to build a stand-out portfolio from scratch even with zero prior experience.\n"
            "3. Live Q&A with Senior Mentors from leading tech firms.\n\n"
            "🗓️ **Date:** This Saturday, 5:00 PM WAT\n"
            "📍 **Location:** Live Private Zoom Link\n\n"
            "Click below to reserve your complimentary VIP pass before registrations fill up!"
        ),
        "cta_text": "Claim Your Free VIP Pass",
        "cta_url": "https://tektutors.com.ng/registration"
    },

    # =========================================================================
    # 4. PROMOTIONAL & SCHOLARSHIP TEMPLATES
    # =========================================================================
    {
        "id": "weekend_scholarship_flash",
        "title": "🎟️ Weekend 20% Tuition Scholarship Flash",
        "category": "promotional",
        "badge": "20% Scholarship",
        "subject": "🎟️ Flash Offer: Claim your 20% Tuition Scholarship for {{course}}",
        "body": (
            "Hi {{name}},\n\n"
            "For this weekend only, TekTutors is granting a special **20% tuition scholarship** to motivated learners enrolling in **{{course}}**!\n\n"
            "**What This Means For You:**\n"
            "• Regular Tuition: ₦100,000 / month\n"
            "• **Your Scholarship Rate: ₦80,000 / month** (Saves ₦20,000 every single month!)\n"
            "• Includes full weekly 1-on-1 private mentorship and capstone projects.\n\n"
            "⏳ **Voucher Expires:** Sunday midnight WAT.\n\n"
            "Apply your scholarship voucher at checkout on our official portal right now:"
        ),
        "cta_text": "Claim 20% Scholarship Voucher",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "scholarship_voucher_activation",
        "title": "🎟️ VIP 20% Scholarship Voucher Activated",
        "category": "promotional",
        "badge": "Voucher Unlocked",
        "subject": "🎉 Special Scholarship Approved: Save ₦20,000 on {{course}}!",
        "body": (
            "Hi {{name}},\n\n"
            "Congratulations! Your eligibility for the **TekTutors 20% Fast-Action Scholarship** has been confirmed for **{{course}}**.\n\n"
            "**Scholarship Voucher Code:** `TEK-EARLY20`\n\n"
            "**Your Discounted Rate:**\n"
            "• Standard Tuition: ₦100,000 / month\n"
            "• **Your Scholarship Rate: ₦80,000 / month** (Saves ₦20,000 every single month!)\n\n"
            "To guarantee mentor availability, this scholarship voucher is active for the next **48 hours only**.\n\n"
            "Redeem your voucher code directly at registration checkout before slots are filled:"
        ),
        "cta_text": "Redeem 20% Voucher Now",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "installment_plan_special",
        "title": "💳 Zero-Debt Month-to-Month Tuition Special",
        "category": "promotional",
        "badge": "Flexible Payment",
        "subject": "💳 Quality Tech Mentorship, Zero Debt: Flexible Month-to-Month Tuition",
        "body": (
            "Hi {{name}},\n\n"
            "We believe world-class technology education should never require taking on massive debt or paying exorbitant upfront lump sums.\n\n"
            "With TekTutors' **Month-to-Month Plan**, you simply invest **₦100,000 / month** as you learn. Pause or continue at your own pace with zero penalties.\n\n"
            "Plus, if you ever decide to pay upfront, enjoy an immediate **10% full-tuition rebate** (₦90,000)!\n\n"
            "Check out our transparent fee structure and start your personalized 1-on-1 training today."
        ),
        "cta_text": "View Flexible Payment Options",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "priority_mentor_bonus",
        "title": "⚡ Early-Bird Priority Mentor Allocation",
        "category": "promotional",
        "badge": "VIP Mentor",
        "subject": "⚡ Early-Bird Perk: Priority Senior Mentor Selection for {{course}}",
        "body": (
            "Hi {{name}},\n\n"
            "Ready to fast-track your tech career? Enroll in **{{course}}** within the next 48 hours and unlock our **Priority Mentor Allocation Perk**.\n\n"
            "You will be paired directly with a Senior Practitioner (5+ years industry experience at multinational technology companies) who will customize your project roadmap to match your target job openings.\n\n"
            "Click below to secure your mentor allocation before priority slots are filled."
        ),
        "cta_text": "Lock In Senior Mentor",
        "cta_url": "https://tektutors.com.ng/registration"
    },

    # =========================================================================
    # 5. STRATEGIC CONVERSION, JAPA & MENTORSHIP SPECIAL CAMPAIGNS
    # =========================================================================
    {
        "id": "japa_global_remote_blueprint",
        "title": "🌍 Japa & Global Remote Career Blueprint ($/£ Salaries & Visas)",
        "category": "marketing",
        "badge": "Japa Blueprint",
        "subject": "The Japa Blueprint: How {{course}} Unlocks Global Remote Roles & Tech Visa Sponsorship",
        "body": (
            "Hi {{name}},\n\n"
            "Are you planning to relocate abroad or land high-paying global remote roles earning in foreign currency ($/£)?\n\n"
            "Here is the unfiltered truth about tech hiring in the UK, Canada, the US, and Europe:\n"
            "**Foreign recruiters and visa authorities don't care about certificates of completion.** What they demand is **verified proof of practical execution and production-grade projects.**\n\n"
            "### 🌍 How TekTutors Prepares You for Japa & Global Remote Success:\n"
            "• **International ATS-Compliant CV Optimization:** Tailored specifically for global platforms (LinkedIn, Wellfound, Otta, Indeed UK/Canada).\n"
            "• **3 Enterprise-Grade GitHub Repositories:** Code reviews from active Senior Practitioners ensuring your GitHub looks like an experienced mid-level engineer.\n"
            "• **Tech Visa Sponsorship Readiness:** Direct guidance on positioning your portfolio for UK Global Talent Visa or Canada Express Entry tech streams.\n"
            "• **High-Yield Dollar Earnings:** Global junior-to-mid remote roles currently compensate **$1,500 – $3,500 / month (₦2,250,000+)**.\n\n"
            "Whether your dream is relocating with your family or earning in hard currency from the comfort of your home, our 1-on-1 mentorship gives you the exact competitive edge needed.\n\n"
            "Want to see our international placement roadmap or have questions about how we support your transition?\n\n"
            "👉 **[Chat directly with Tara on WhatsApp to discuss your Japa goals]({{tara_chat_url}})**\n\n"
            "Or secure your private mentor allocation before weekend onboarding closes:"
        ),
        "cta_text": "Explore Japa & Remote Curriculum",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "mentorship_vs_bootcamp_advantage",
        "title": "🤝 1-on-1 Mentorship Revolution: Why Solo Tutorials Fail",
        "category": "conversion",
        "badge": "1-on-1 Mentorship",
        "subject": "Why 1-on-1 Screen Sharing Changes Everything ({{course}})",
        "body": (
            "Hi {{name}},\n\n"
            "Have you ever spent 3 days stuck on a single syntax error in Python or a broken DAX calculation in Power BI — feeling so frustrated that you closed your laptop and gave up?\n\n"
            "You are not alone. **Over 90% of students drop out of typical online courses.**\n\n"
            "### ❌ The Old Bootcamp Trap:\n"
            "You are dumped into a 50-person Zoom call with a lecturer rushing through 100 slides. When your code breaks, nobody stops to help you. You leave feeling inadequate and confused.\n\n"
            "### ✅ The TekTutors 1-on-1 Screen-Sharing Advantage:\n"
            "• **100% Private Video Sessions:** Every session is just you and a Senior Industry Practitioner working directly on your screen.\n"
            "• **Live Line-by-Line Debugging:** Whenever an error pops up, your mentor guides you through fixing it immediately.\n"
            "• **Zero Peer Intimidation:** Ask every question as many times as you need without feeling judged.\n"
            "• **Custom Learning Pace:** Speed up through concepts you understand and take extra time on complex topics.\n\n"
            "You don't need a math or computer science degree. You just need a patient, world-class mentor dedicated to your career.\n\n"
            "Have questions about how our 1-on-1 sessions work?\n\n"
            "👉 **[Chat directly with Tara on WhatsApp for instant answers]({{tara_chat_url}})**\n\n"
            "Ready to get paired with your assigned senior practitioner?"
        ),
        "cta_text": "Meet Your Senior Mentor",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "tektutors_irresistible_tuition_offer",
        "title": "🎁 Irresistible Tuition Plan: ₦100k/Mo, ₦90k Upfront Rebate & ₦35k Bonus",
        "category": "promotional",
        "badge": "Tuition Offer",
        "subject": "Our Flexible Tuition Plan & Free ₦35,000 Career Bonus ({{course}})",
        "body": (
            "Hi {{name}},\n\n"
            "We believe acquiring high-income tech skills should empower you financially — never put you into crushing debt.\n\n"
            "That is why TekTutors offers the most flexible, learner-friendly tuition structure in the market:\n\n"
            "### 💳 1. Flexible Month-to-Month Tuition:\n"
            "Invest just **₦100,000 / month** as you learn. No lock-in contracts. You have total freedom to pause or cancel anytime if your schedule changes.\n\n"
            "### 🎁 2. Upfront 10% Cash Rebate (Save ₦10,000):\n"
            "Choose full prepayment at checkout and pay just **₦90,000** today (save ₦10,000 immediately).\n\n"
            "### 🌟 Fast-Action Career Bonus (Valued at ₦35,000):\n"
            "Enroll this week and unlock a **Free 1-on-1 CV Optimization & LinkedIn Makeover** with our Senior Hiring Consultant to get you noticed by tech recruiters.\n\n"
            "### 📊 The ROI Math:\n"
            "Junior data and AI practitioners earn between **₦350,000 to ₦750,000/month** locally, and **$1,500 – $3,000/month** remotely. Your entire training investment pays for itself within **under 3 weeks** of your first salary.\n\n"
            "Need help choosing a payment plan or setting up flexible installments?\n\n"
            "👉 **[Chat directly with Tara on WhatsApp to claim your bonus]({{tara_chat_url}})**\n\n"
            "Or lock in your upfront rebate and secure your mentor today:"
        ),
        "cta_text": "Claim Tuition Discount & Enroll",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "non_tech_career_pivot_blueprint",
        "title": "💼 Career Switch Blueprint for Bankers, Accountants & Ops Pros",
        "category": "conversion",
        "badge": "Career Pivot",
        "subject": "Zero Coding Experience? How Finance & Ops Professionals Switch to ₦650k/mo Data Roles",
        "body": (
            "Hi {{name}},\n\n"
            "Are you currently working in banking, accounting, customer service, operations, or marketing and feeling trapped in routine spreadsheets?\n\n"
            "Here is a secret tech hiring managers won't tell you:\n"
            "**You already possess the most difficult skill to teach — business commercial acumen.**\n\n"
            "When you pair your commercial intuition with **SQL querying, Power BI interactive reporting, and automated Python workflows**, you become 5x more valuable than a pure computer science graduate with zero business context.\n\n"
            "### 💼 How TekTutors Bridges Your Transition:\n"
            "• **Tailored 1-on-1 Coaching:** We explain technical concepts using relatable business cases (customer churn, sales forecasting, revenue reporting).\n"
            "• **Weekend & Evening Friendly:** Keep your full-time job while building your new portfolio.\n"
            "• **100% Practical Screen-Shares:** You learn by building real dashboards, not memorizing abstract theory.\n"
            "• **Risk-Free Month-to-Month:** Invest ₦100,000/month (or ₦90,000 upfront) with full control over your timeline.\n\n"
            "Worried about your background or whether this is right for you?\n\n"
            "👉 **[Chat directly with Tara on WhatsApp for a quick profile assessment]({{tara_chat_url}})**\n\n"
            "Or take the leap and start your personalized 1-on-1 mentorship today:"
        ),
        "cta_text": "Start Your Non-Tech Career Switch",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "cost_of_waiting_inflation",
        "title": "⏳ The True Cost of Inaction: Inflation vs High-Income Tech Skills",
        "category": "conversion",
        "badge": "Emotional Wakeup",
        "subject": "The True Cost of Waiting: Where Will You Be in 6 Months, {{name}}?",
        "body": (
            "Hi {{name}},\n\n"
            "Let's have an honest conversation about time and money.\n\n"
            "With rising inflation and currency devaluation, relying on a single static income stream is one of the riskiest positions in today's economy.\n\n"
            "Six months from today, one of two things will happen:\n"
            "**Scenario A:** You continue doing what you've always done. You watch prices climb while your earnings remain unchanged. Another year passes wishing you had made a move.\n"
            "**Scenario B:** You invested 12 weeks into private 1-on-1 mentorship with a Senior Practitioner. You mastered SQL, Power BI, and Python. You have 3 verified enterprise projects on your GitHub and recruiters reaching out on LinkedIn.\n\n"
            "The difference between Scenario A and Scenario B isn't talent or luck — it is the decision to take decisive action today.\n\n"
            "With our flexible **₦100,000/month** plan (or **₦90,000 upfront**, saving ₦10,000), world-class tech mentorship has never been more accessible.\n\n"
            "Ready to take control of your financial future?\n\n"
            "👉 **[Chat directly with Tara on WhatsApp to take the first step]({{tara_chat_url}})**\n\n"
            "Or enroll now and begin your live onboarding this weekend:"
        ),
        "cta_text": "Invest in Your Career Growth",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "id": "mentor_slot_expiring_final_notice",
        "title": "⚡ Final Notice: Reserved 1-on-1 Mentor Slot Expiring",
        "category": "conversion",
        "badge": "Slot Expiring",
        "subject": "Final Notice: Your Reserved Mentor Slot is Expiring, {{name}}",
        "body": (
            "Hi {{name}},\n\n"
            "Because TekTutors is committed to **100% private 1-on-1 live screen-sharing**, our senior industry mentors can only work with a maximum of **4 new learners per month**.\n\n"
            "Our admissions team has held an onboarding slot for you in **{{course}}**, but our system is scheduled to release unconfirmed seats to our waiting list tomorrow morning.\n\n"
            "### Everything Included in Your Onboarding:\n"
            "✅ Live private 1-on-1 mentorship with an active Senior Practitioner (flexible evening & weekend slots)\n"
            "✅ 3 employer-grade portfolio capstone projects published on GitHub and LinkedIn\n"
            "✅ Free ₦35,000 1-on-1 CV Optimization & Tech Interview Coaching\n"
            "✅ Flexible ₦100,000/month or ₦90,000 upfront (save ₦10,000 immediately)\n\n"
            "Don't let your slot slip away to the waitlist.\n\n"
            "👉 **[Chat directly with Tara on WhatsApp to hold your mentor slot]({{tara_chat_url}})**\n\n"
            "Or complete your registration immediately before your reservation expires:"
        ),
        "cta_text": "Lock In Your Mentor Slot Now",
        "cta_url": "https://tektutors.com.ng/registration"
    }
]

# =====================================================================
# EDITABLE EMAIL BRANDING, HEADER & FOOTER SYSTEM
# =====================================================================

_EMAIL_BRANDING_CACHE: Dict[str, Any] = {
    "header_title": "TekTutors",
    "header_subtitle": "Practical Data Analytics & AI Mentorship Academy",
    "header_badge": "Live 1-on-1 Mentorship",
    "primary_color": "#eb6711",
    "footer_contact": "Have questions or need help? Reply to this email or message Tara on WhatsApp: +234 911 212 0531",
    "footer_copyright": "TekTutors Academy. All rights reserved.",
    "footer_extra": "",
    "custom_header_html": None,
    "custom_footer_html": None
}

def get_email_branding_cache() -> Dict[str, Any]:
    """Return a copy of the active in-memory email branding configuration."""
    return dict(_EMAIL_BRANDING_CACHE)

def update_email_branding_cache(new_config: Dict[str, Any]) -> Dict[str, Any]:
    """Update the in-memory email branding configuration."""
    global _EMAIL_BRANDING_CACHE
    for k, v in new_config.items():
        if k in _EMAIL_BRANDING_CACHE:
            _EMAIL_BRANDING_CACHE[k] = v
    return dict(_EMAIL_BRANDING_CACHE)

async def sync_email_branding_from_db():
    """Load and synchronize email branding from SystemConfig database table into memory."""
    try:
        from app.database import AsyncSessionLocal
        from app.models import SystemConfig
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            stmt = select(SystemConfig).limit(1)
            res = await db.execute(stmt)
            cfg = res.scalar_one_or_none()
            if cfg:
                update_email_branding_cache({
                    "header_title": cfg.email_header_title or "TekTutors",
                    "header_subtitle": cfg.email_header_subtitle or "Practical Data Analytics & AI Mentorship Academy",
                    "header_badge": cfg.email_header_badge or "Live 1-on-1 Mentorship",
                    "primary_color": cfg.email_primary_color or "#eb6711",
                    "footer_contact": cfg.email_footer_contact or "Have questions or need help? Reply to this email or message Tara on WhatsApp: +234 911 212 0531",
                    "footer_copyright": cfg.email_footer_copyright or "TekTutors Academy. All rights reserved.",
                    "footer_extra": cfg.email_footer_extra or "",
                    "custom_header_html": cfg.email_custom_header_html,
                    "custom_footer_html": cfg.email_custom_footer_html
                })
                logger.info(f"Synchronized email branding configuration from DB (Header: '{_EMAIL_BRANDING_CACHE['header_title']}')")
    except Exception as e:
        logger.warning(f"Note: Could not sync email branding from DB ({e})")


def render_branded_email_html(
    subject: str,
    body_markdown: str,
    cta_text: str = "Register Online",
    cta_url: str = "https://tektutors.com.ng/registration",
    recipient_name: str = "Student",
    header_title: Optional[str] = None,
    header_subtitle: Optional[str] = None,
    header_badge: Optional[str] = None,
    primary_color: Optional[str] = None,
    footer_contact: Optional[str] = None,
    footer_copyright: Optional[str] = None,
    footer_extra: Optional[str] = None,
    custom_header_html: Optional[str] = None,
    custom_footer_html: Optional[str] = None,
    tara_chat_url: Optional[str] = None
) -> str:
    """
    Render modern, responsive HTML email matching TekTutors visual identity with
    fully editable and configurable header, footer, color accents, and custom HTML overrides.
    Every email includes an intelligent, direct interactive link and callout to chat with Tara on WhatsApp.
    """
    cfg = get_email_branding_cache()

    # Resolve active values (arguments override cache defaults)
    active_primary_color = (primary_color or cfg.get("primary_color") or "#eb6711").strip()
    active_header_title = header_title if header_title is not None else (cfg.get("header_title") or "TekTutors")
    active_header_subtitle = header_subtitle if header_subtitle is not None else (cfg.get("header_subtitle") or "")
    active_header_badge = header_badge if header_badge is not None else (cfg.get("header_badge") or "")
    active_footer_contact = footer_contact if footer_contact is not None else (cfg.get("footer_contact") or "")
    active_footer_copyright = footer_copyright if footer_copyright is not None else (cfg.get("footer_copyright") or "TekTutors Academy. All rights reserved.")
    active_footer_extra = footer_extra if footer_extra is not None else (cfg.get("footer_extra") or "")
    active_custom_header = custom_header_html if custom_header_html is not None else cfg.get("custom_header_html")
    active_custom_footer = custom_footer_html if custom_footer_html is not None else cfg.get("custom_footer_html")
    
    # Resolve active Tara WhatsApp chat link
    active_tara_chat_url = (tara_chat_url or "https://wa.me/2349112120531?text=Hi%20Tara%2C%20I%20have%20questions%20about%20learning%20with%20TekTutors.").strip()

    # Pre-substitute tara_chat_url token if in body
    rendered_body = body_markdown.replace("{{tara_chat_url}}", active_tara_chat_url)

    # Format Markdown body paragraphs and list items
    paragraphs = [p.strip() for p in rendered_body.split("\n\n") if p.strip()]
    formatted_paras = []
    
    for p in paragraphs:
        if any(p.startswith(prefix) for prefix in ["•", "-", "✅", "1.", "2.", "3."]):
            lines = p.split("\n")
            items = []
            for line in lines:
                clean_line = re.sub(r'^[•\-\*✅\d\.]+\s*', '', line.strip())
                clean_line = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', clean_line)
                clean_line = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', clean_line)
                # Convert markdown links [text](url) to styled anchor tags
                clean_line = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank" style="color: ' + active_primary_color + r'; font-weight: 600; text-decoration: underline;">\1</a>', clean_line)
                items.append(f'<li style="margin-bottom: 8px; line-height: 1.6;">{clean_line}</li>')
            formatted_paras.append(f'<ul style="padding-left: 20px; color: #334155; margin: 16px 0;">{"".join(items)}</ul>')
        else:
            p_html = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', p)
            p_html = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', p_html)
            # Convert markdown links [text](url) to styled anchor tags
            p_html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank" style="color: ' + active_primary_color + r'; font-weight: 600; text-decoration: underline;">\1</a>', p_html)
            p_html = p_html.replace("\n", "<br>")
            formatted_paras.append(f'<p style="margin: 0 0 16px 0; line-height: 1.65; color: #334155; font-size: 15px;">{p_html}</p>')

    body_content_html = "\n".join(formatted_paras)

    # 1. Render Header
    if active_custom_header and active_custom_header.strip():
        header_markup = active_custom_header.strip()
    else:
        # Styled title: if 'TekTutors', keep the iconic orange highlight span
        if active_header_title.strip().lower() == "tektutors":
            styled_title = f'Tek<span style="color: {active_primary_color};">Tutors</span>'
        else:
            styled_title = active_header_title.strip()

        subtitle_markup = f'<div style="font-size: 12px; color: #94a3b8; margin-top: 4px; font-weight: 500;">{active_header_subtitle.strip()}</div>' if active_header_subtitle.strip() else ''
        
        badge_markup = ""
        if active_header_badge.strip():
            badge_markup = f"""<td align="right">
              <span style="display: inline-block; padding: 4px 10px; background: rgba(235, 103, 17, 0.18); border: 1px solid {active_primary_color}; color: {active_primary_color}; font-size: 11px; font-weight: 700; border-radius: 20px; text-transform: uppercase; letter-spacing: 0.5px;">
                {active_header_badge.strip()}
              </span>
            </td>"""

        header_markup = f"""<!-- Header Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 32px 28px; text-align: left; border-bottom: 3px solid {active_primary_color};">
              <table width="100%" role="presentation">
                <tr>
                  <td>
                    <div style="font-size: 22px; font-weight: 800; color: #ffffff; letter-spacing: -0.5px;">
                      {styled_title}
                    </div>
                    {subtitle_markup}
                  </td>
                  {badge_markup}
                </tr>
              </table>
            </td>
          </tr>"""

    # 2. Render Footer
    if active_custom_footer and active_custom_footer.strip():
        footer_markup = active_custom_footer.strip()
    else:
        # Auto-link WhatsApp contact if present and not already linked
        contact_line = active_footer_contact.strip()
        if "<a " not in contact_line:
            # If phone number like +234 ... or 080... found, link it
            phone_match = re.search(r'(\+?234[\s\d\-]+|\b0[789][01]\d{8}\b)', contact_line)
            if phone_match:
                raw_phone = phone_match.group(1)
                num_only = re.sub(r'[^\d]', '', raw_phone)
                if not num_only.startswith("234"):
                    num_only = "234" + num_only.lstrip("0")
                linked_phone = f'<a href="https://wa.me/{num_only}" style="color: #00a884; font-weight: 600; text-decoration: none;">{raw_phone}</a>'
                contact_line = contact_line.replace(raw_phone, linked_phone)

        extra_markup = f'<p style="margin: 8px 0 0 0; font-size: 11px; color: #94a3b8; line-height: 1.4;">{active_footer_extra.strip()}</p>' if active_footer_extra.strip() else ''

        footer_markup = f"""<!-- Footer -->
          <tr>
            <td style="background-color: #f8fafc; padding: 24px 32px; border-top: 1px solid #e2e8f0; text-align: center;">
              <p style="margin: 0 0 8px 0; font-size: 12px; color: #64748b; line-height: 1.5;">
                {contact_line}
              </p>
              <p style="margin: 0; font-size: 11px; color: #94a3b8;">
                &copy; {datetime.datetime.now().year} {active_footer_copyright.strip()} &bull; 
                <a href="https://tektutors.com.ng" style="color: #64748b; text-decoration: none;">tektutors.com.ng</a>
              </p>
              {extra_markup}
            </td>
          </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f1f5f9; padding: 32px 16px;">
    <tr>
      <td align="center">
        <!-- Main Card Container -->
        <table role="presentation" width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.06); border: 1px solid #e2e8f0;">
          
          {header_markup}

          <!-- Email Content Body -->
          <tr>
            <td style="padding: 36px 32px 28px 32px;">
              <h1 style="margin: 0 0 20px 0; font-size: 20px; font-weight: 700; color: #0f172a; line-height: 1.35;">
                {subject}
              </h1>

              {body_content_html}

              <!-- Primary CTA Button -->
              <table role="presentation" cellspacing="0" cellpadding="0" style="margin: 32px 0 16px 0;">
                <tr>
                  <td align="left" style="border-radius: 8px; background: {active_primary_color};">
                    <a href="{cta_url}" target="_blank" style="display: inline-block; padding: 14px 28px; font-size: 15px; font-weight: 700; color: #ffffff; text-decoration: none; border-radius: 8px; letter-spacing: 0.2px;">
                      {cta_text} &rarr;
                    </a>
                  </td>
                </tr>
              </table>

              <!-- Dedicated Chat with Tara on WhatsApp Action Box -->
              <table role="presentation" width="100%" style="background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%); border: 1.5px solid #86efac; border-radius: 10px; margin: 20px 0 24px 0; padding: 18px 20px;">
                <tr>
                  <td>
                    <table role="presentation" width="100%">
                      <tr>
                        <td width="36" valign="top" style="font-size: 26px; line-height: 1; padding-right: 12px;">
                          💬
                        </td>
                        <td valign="top">
                          <div style="font-size: 14px; font-weight: 700; color: #065f46; margin-bottom: 4px;">
                            Have Questions? Chat Directly with Tara on WhatsApp
                            <span style="font-size: 11px; background: rgba(37,211,102,0.22); color: #047857; padding: 2px 8px; border-radius: 12px; margin-left: 6px; font-weight: 700;">+234 911 212 0531</span>
                          </div>
                          <div style="font-size: 13px; color: #047857; line-height: 1.5; margin-bottom: 12px;">
                            Our Admissions Advisor <strong>Tara</strong> is available directly on WhatsApp at <strong>+234 911 212 0531</strong> to discuss course tracks, syllabus roadmaps, flexible installment options, or to get matched with your 1-on-1 mentor.
                          </div>
                          <a href="{active_tara_chat_url}" target="_blank" style="display: inline-block; background-color: #25D366; color: #ffffff; font-size: 13px; font-weight: 700; padding: 10px 22px; border-radius: 6px; text-decoration: none; box-shadow: 0 2px 6px rgba(37,211,102,0.25);">
                            💬 Chat with Tara on WhatsApp (+234 911 212 0531) &rarr;
                          </a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- Trust Callout Box -->
              <table role="presentation" width="100%" style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-top: 16px;">
                <tr>
                  <td>
                    <div style="font-size: 13px; font-weight: 700; color: #0f172a; margin-bottom: 4px;">
                      🎯 The TekTutors Difference
                    </div>
                    <div style="font-size: 12px; color: #64748b; line-height: 1.5;">
                      Flexible month-to-month billing (₦100,000/mo) • Dedicated 1-on-1 industry practitioner • Zero pre-recorded videos • 3 employer-ready portfolio projects.
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          {footer_markup}

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

class IPv4SMTP_SSL(smtplib.SMTP_SSL):
    """Guarantees pure IPv4 DNS resolution and connection to prevent IPv6 'Network is unreachable' errors."""
    def _get_socket(self, host, port, timeout):
        err = None
        for res in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
            af, socktype, proto, canonname, sa = res
            sock = None
            try:
                sock = socket.socket(af, socktype, proto)
                if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                    sock.settimeout(timeout)
                sock.connect(sa)
                return self.context.wrap_socket(sock, server_hostname=self._host)
            except OSError as _err:
                err = _err
                if sock is not None:
                    sock.close()
        if err is not None:
            raise err
        raise OSError(f"Could not resolve IPv4 address for {host}")


class IPv4SMTP(smtplib.SMTP):
    """Guarantees pure IPv4 DNS resolution and connection to prevent IPv6 'Network is unreachable' errors."""
    def _get_socket(self, host, port, timeout):
        err = None
        for res in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
            af, socktype, proto, canonname, sa = res
            sock = None
            try:
                sock = socket.socket(af, socktype, proto)
                if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                    sock.settimeout(timeout)
                sock.connect(sa)
                return sock
            except OSError as _err:
                err = _err
                if sock is not None:
                    sock.close()
        if err is not None:
            raise err
        raise OSError(f"Could not resolve IPv4 address for {host}")


def _connect_smtp_server_resilient(host: str, port: int, is_ssl: bool, timeout: int = 15):
    """
    Connect to SMTP server strictly prioritizing IPv4 to completely prevent
    'Network is unreachable' [Errno 101 / WinError 10051] when running on dual-stack
    cloud networks (Railway, Docker, etc.) where IPv6 is configured without public routes.
    """
    # 1. First attempt: Strict IPv4 resolution & connection
    try:
        if is_ssl:
            return IPv4SMTP_SSL(host, port, timeout=timeout)
        else:
            server = IPv4SMTP(host, port, timeout=timeout)
            if settings.SMTP_USE_TLS or port == 587:
                server.starttls()
            return server
    except (OSError, smtplib.SMTPConnectError, socket.error) as ipv4_err:
        logger.warning(f"Strict IPv4 SMTP connection to {host}:{port} failed ({ipv4_err}). Retrying standard socket...")

    # 2. Second attempt: Fallback to standard system socket
    if is_ssl:
        return smtplib.SMTP_SSL(host, port, timeout=timeout)
    else:
        server = smtplib.SMTP(host, port, timeout=timeout)
        if settings.SMTP_USE_TLS or port == 587:
            server.starttls()
        return server



def _send_smtp_email_sync(to_email: str, subject: str, html_content: str, text_content: str) -> bool:
    """Internal helper to dispatch email over SMTP synchronously with resilient failover."""
    if not settings.SMTP_HOST:
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to_email

    msg.attach(MIMEText(text_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    primary_port = settings.SMTP_PORT or 465
    primary_ssl = (primary_port == 465)
    fallback_port = 587 if primary_ssl else 465
    fallback_ssl = not primary_ssl

    attempts = [
        (primary_port, primary_ssl),
        (fallback_port, fallback_ssl)
    ]

    server = None
    last_err = None

    for port, is_ssl in attempts:
        try:
            server = _connect_smtp_server_resilient(settings.SMTP_HOST, port, is_ssl, timeout=6)
            break
        except Exception as e:
            logger.warning(f"SMTP connection to {settings.SMTP_HOST}:{port} failed ({e}). Trying fallback...")
            last_err = e

    if not server:
        raise last_err or RuntimeError(f"Could not connect to {settings.SMTP_HOST} on ports {primary_port} or {fallback_port}.")

    try:
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            clean_password = settings.SMTP_PASSWORD.replace(" ", "").strip()
            server.login(settings.SMTP_USER, clean_password)

        server.sendmail(settings.SMTP_FROM_EMAIL, [to_email], msg.as_string())
        server.quit()
        return True
    except Exception as dispatch_err:
        try:
            server.close()
        except Exception:
            pass
        raise dispatch_err

async def _send_resend_email_async(to_email: str, subject: str, html_content: str, text_content: str) -> bool:
    """Dispatch email via Resend HTTPS API (Port 443) - immune to cloud host SMTP port blocks."""
    import httpx
    api_key = (os.getenv("RESEND_API_KEY") or settings.RESEND_API_KEY or "").strip().strip('"').strip("'")
    if not api_key:
        raise ValueError("RESEND_API_KEY is not configured.")

    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    from_email = (os.getenv("SMTP_FROM_EMAIL") or settings.SMTP_FROM_EMAIL or "onboarding@resend.dev").strip()
    from_name = (os.getenv("SMTP_FROM_NAME") or settings.SMTP_FROM_NAME or "TekTutors").strip()
    if "@gmail.com" in from_email.lower():
        from_header = f"{from_name} <onboarding@resend.dev>"
    else:
        from_header = f"{from_name} <{from_email}>"

    payload = {
        "from": from_header,
        "to": [to_email],
        "subject": subject,
        "html": html_content,
        "text": text_content
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code in (200, 201):
            logger.info(f"Resend HTTPS dispatch succeeded to {to_email}")
            return True
        elif resp.status_code == 403 and ("domain" in resp.text.lower() and "verify" in resp.text.lower()):
            if "not verified" in resp.text.lower():
                err_msg = (
                    f"Resend Domain Verification Required: The sender domain '{from_email}' is not verified yet on Resend. "
                    "Please add and verify your domain at https://resend.com/domains (add the DNS records in your domain manager). "
                    "To test immediately before DNS verification, set SMTP_FROM_EMAIL=onboarding@resend.dev to send to your account email."
                )
            else:
                err_msg = (
                    "Resend Sandbox Restriction: Testing emails with 'onboarding@resend.dev' can only be sent to your "
                    "registered Resend account email. To send to student/lead emails, verify your domain at https://resend.com/domains."
                )
            logger.error(err_msg)
            raise RuntimeError(err_msg)
        else:
            raise RuntimeError(f"Resend API error {resp.status_code}: {resp.text}")


async def _send_brevo_email_async(to_email: str, subject: str, html_content: str, text_content: str) -> bool:
    """Dispatch email via Brevo HTTPS API (Port 443) - immune to cloud host SMTP port blocks."""
    import httpx
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "api-key": settings.BREVO_API_KEY.strip(),
        "Content-Type": "application/json"
    }
    payload = {
        "sender": {"name": settings.SMTP_FROM_NAME, "email": settings.SMTP_FROM_EMAIL},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content,
        "textContent": text_content
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code in (200, 201):
            logger.info(f"Brevo HTTPS dispatch succeeded to {to_email}")
            return True
        else:
            raise RuntimeError(f"Brevo API error {resp.status_code}: {resp.text}")


async def send_email_async(
    to_email: Optional[str] = None,
    to_name: Optional[str] = None,
    subject: str = "",
    body_markdown: str = "",
    campaign_type: str = "follow_up",
    lead_id: Optional[int] = None,
    cta_text: str = "Register Online",
    cta_url: str = "https://tektutors.com.ng/registration",
    course_name: str = "Data Analytics & AI",
    recipient_email: Optional[str] = None,
    recipient_name: Optional[str] = None,
    tara_chat_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send personalized follow-up, marketing, or promotional email.
    Substitutes tokens, renders branded HTML, dispatches via HTTPS API / SMTP (or simulated mode),
    and records an audit log in EmailLog. Every email contains direct personalized links to chat with Tara.
    """
    import urllib.parse
    target_email = to_email or recipient_email or ""
    target_name = to_name or recipient_name or "Student"
    clean_email = target_email.strip().lower()
    clean_name = target_name.strip() if target_name else "Student"
    
    # 1. Personalize subject and body
    from app.cache import normalize_course_name
    clean_course = normalize_course_name(course_name) or "Data Analytics & BI Accelerator"

    # Construct personalized Tara WhatsApp chat link
    enc_course = urllib.parse.quote(clean_course)
    enc_name = urllib.parse.quote(clean_name)
    resolved_tara_url = (tara_chat_url or f"https://wa.me/2349112120531?text=Hi%20Tara%2C%20I%20am%20{enc_name}.%20I%20got%20your%20email%20about%20{enc_course}%20and%20I%20want%20to%20learn%20with%20TekTutors.").strip()

    personalized_subject = subject.replace("{{name}}", clean_name).replace("{{course}}", clean_course)
    personalized_body = (
        body_markdown
        .replace("{{name}}", clean_name)
        .replace("{{course}}", clean_course)
        .replace("{{registration_url}}", cta_url)
        .replace("{{tara_chat_url}}", resolved_tara_url)
    )
    
    # 2. Render branded HTML template with Tara WhatsApp action card
    html_content = render_branded_email_html(
        subject=personalized_subject,
        body_markdown=personalized_body,
        cta_text=cta_text,
        cta_url=cta_url,
        recipient_name=clean_name,
        tara_chat_url=resolved_tara_url
    )

    status = "sent"
    error_message = None

    # 3. Multi-tier Dispatch Engine:
    #    Tier 1: Resend HTTPS API (Port 443) - never blocked by cloud firewalls
    #    Tier 2: Brevo HTTPS API (Port 443)
    #    Tier 3: Resilient IPv4 Direct SMTP (Port 465 / 587)
    #    Tier 4: Local preview simulation mode
    active_resend_key = (os.getenv("RESEND_API_KEY") or settings.RESEND_API_KEY or "").strip()
    active_brevo_key = (os.getenv("BREVO_API_KEY") or settings.BREVO_API_KEY or "").strip()
    is_test_recipient = clean_email.endswith("@example.com") or clean_email.endswith(".test") or os.getenv("APP_ENV") == "testing"

    if is_test_recipient and not (active_resend_key and not clean_email.endswith("@example.com")):
        # In test environments or for dummy addresses, log and succeed without failing on external API validation
        logger.info(f"Simulated email dispatch to test recipient {clean_email} (Subject: {personalized_subject})")
        status = "delivered"
    elif active_resend_key:
        try:
            await _send_resend_email_async(clean_email, personalized_subject, html_content, personalized_body)
            logger.info(f"Successfully sent live email via Resend HTTPS API to {clean_email}")
        except Exception as e:
            logger.error(f"Resend API error delivering to {clean_email}: {e}")
            status = "failed"
            error_message = str(e)
    elif active_brevo_key:
        try:
            await _send_brevo_email_async(clean_email, personalized_subject, html_content, personalized_body)
            logger.info(f"Successfully sent live email via Brevo HTTPS API to {clean_email}")
        except Exception as e:
            logger.error(f"Brevo API error delivering to {clean_email}: {e}")
            status = "failed"
            error_message = str(e)
    elif settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD:
        try:
            await asyncio.to_thread(
                _send_smtp_email_sync,
                clean_email,
                personalized_subject,
                html_content,
                personalized_body
            )
            logger.info(f"Successfully sent live SMTP email to {clean_email} (Subject: {personalized_subject})")
        except Exception as e:
            err_str = str(e)
            if "unreachable" in err_str.lower() or "timeout" in err_str.lower() or "errno 101" in err_str.lower() or "10051" in err_str:
                err_str += " (Cloud Firewall Block: Raw outbound SMTP ports 25/465/587 are blocked on Railway Hobby/Trial plans. Configure RESEND_API_KEY to dispatch over HTTPS Port 443 or upgrade to Railway Pro)."
            logger.error(f"SMTP Error delivering to {clean_email}: {err_str}")
            status = "failed"
            error_message = err_str
    elif settings.SMTP_HOST:
        err_msg = "SMTP_USER or SMTP_PASSWORD is not configured in environment variables."
        logger.error(err_msg)
        status = "failed"
        error_message = err_msg
    else:
        # Simulated mode for development/preview
        logger.info(f"[Email Simulation] Dispatched '{campaign_type}' email to {clean_email} ({personalized_subject})")
        status = "delivered"

    # 4. Save audit trail in database
    log_id = None
    try:
        async with AsyncSessionLocal() as db:
            log_entry = EmailLog(
                lead_id=lead_id,
                recipient_email=clean_email,
                recipient_name=clean_name,
                campaign_type=campaign_type,
                subject=personalized_subject,
                body_html=html_content,
                status=status,
                error_message=error_message,
                sent_at=datetime.datetime.now()
            )
            db.add(log_entry)
            await db.commit()
            log_id = log_entry.id
    except Exception as err:
        logger.error(f"Error logging email delivery to database: {err}")

    return {
        "status": status,
        "log_id": log_id,
        "recipient_email": clean_email,
        "recipient_name": clean_name,
        "subject": personalized_subject,
        "campaign_type": campaign_type,
        "is_simulated": not bool(settings.SMTP_HOST),
        "error_message": error_message
    }


async def dispatch_engagement_email(
    lead_id: Optional[int] = None,
    trigger_event: str = "syllabus",
    course_name: str = "Data Analytics & BI Accelerator",
    recipient_email: Optional[str] = None,
    recipient_name: Optional[str] = None,
    custom_notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Intelligently dispatch an email sequence based on user engagement milestone:
    - 'syllabus': Curriculum and week-by-week roadmap delivery
    - 'consultation': 1-on-1 advisor discovery call confirmation & prep guide
    - 'scholarship': 20% tuition scholarship voucher & upfront discount
    - 'invoice': Official registration checkout link & payment options
    - 'reengagement': Student transformation story & seat reservation check-in
    """
    target_email = recipient_email
    target_name = recipient_name or "Student"
    from app.cache import normalize_course_name
    target_course = normalize_course_name(course_name) or "Data Analytics & BI Accelerator"

    # If email missing and lead_id provided, look up lead from database
    if (not target_email or not target_email.strip()) and lead_id:
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(Lead).where(Lead.id == lead_id)
                res = await db.execute(stmt)
                lead = res.scalar_one_or_none()
                if lead and lead.email:
                    target_email = lead.email
                    if lead.name and target_name == "Student":
                        target_name = lead.name
                    if lead.course_interest:
                        norm = normalize_course_name(lead.course_interest)
                        if norm:
                            target_course = norm
        except Exception as e:
            logger.warning(f"Error fetching lead #{lead_id} for engagement email: {e}")

    if not target_email or "@" not in target_email:
        logger.info(f"Engagement email skipped for trigger '{trigger_event}': No valid email address.")
        return {
            "status": "skipped",
            "message": f"Engagement trigger '{trigger_event}' skipped: No email address available for lead.",
            "trigger_event": trigger_event
        }

    template_map = {
        "syllabus": "syllabus_delivery_followup",
        "consultation": "consultation_booking_confirmation",
        "scholarship": "scholarship_voucher_activation",
        "invoice": "checkout_invoice_delivery",
        "reengagement": "incomplete_application_followup"
    }

    template_id = template_map.get(trigger_event, "syllabus_delivery_followup")
    tpl = next((t for t in PREBUILT_EMAIL_TEMPLATES if t["id"] == template_id), PREBUILT_EMAIL_TEMPLATES[1])

    body_text = tpl["body"]
    if custom_notes:
        body_text += f"\n\n**Advisors Note:**\n{custom_notes}"

    return await send_email_async(
        recipient_email=target_email,
        recipient_name=target_name,
        subject=tpl["subject"],
        body_markdown=body_text,
        campaign_type=tpl.get("category", "follow_up"),
        lead_id=lead_id,
        cta_text=tpl.get("cta_text", "Register Online"),
        cta_url=tpl.get("cta_url", "https://tektutors.com.ng/registration"),
        course_name=target_course
    )


# =========================================================================
# 4. DAILY AUTOMATED FOLLOW-UP DRIP SEQUENCE (DAYS 1-7)
# =========================================================================
DAILY_DRIP_SEQUENCE = [
    {
        "day": 1,
        "title": "What Makes TekTutors Different: 100% Live 1-on-1 Mentorship",
        "subject": "Why 1-on-1 Screen Sharing Changes Everything ({{course}})",
        "body": (
            "Hi {{name}},\n\n"
            "Yesterday, we shared your curriculum roadmap for **{{course}}**.\n\n"
            "Today, we want to talk honestly about why 90% of students drop out of typical online courses — and how TekTutors solves it completely.\n\n"
            "### ❌ The Old Bootcamp Trap:\n"
            "You get dumped into a 50-person Zoom call with a lecturer talking non-stop for 2 hours. If your SQL script errors out or your Power BI model breaks, nobody stops to help. You're left stranded and frustrated.\n\n"
            "### ✅ The TekTutors 1-on-1 Advantage:\n"
            "• **100% Private Screen Shares:** Every single session is just you and a Senior Industry Practitioner working directly on your code.\n"
            "• **Zero Embarrassment:** Ask every question as many times as you need without peer pressure.\n"
            "• **Custom Learning Pace:** Fast-track areas you understand quickly, and spend extra time mastering difficult concepts.\n"
            "• **Flexible Scheduling:** Sessions fit your working lifestyle on weekday evenings or weekends.\n\n"
            "You don't need a computer science background. You just need a patient, world-class mentor dedicated to your career.\n\n"
            "Have questions about how private mentor sessions work?\n\n"
            "💬 **[Chat directly with Tara on WhatsApp to discuss your goals & schedule]({{tara_chat_url}})**\n\n"
            "Ready to meet your assigned mentor?"
        ),
        "cta_text": "Meet Your Mentor & Enroll",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "day": 2,
        "title": "Our Irresistible Offer: ₦100,000/Month or ₦90,000 Upfront + Free Bonus",
        "subject": "Our Flexible Tuition Plan & Free ₦35,000 Career Bonus ({{course}})",
        "body": (
            "Hi {{name}},\n\n"
            "We believe that acquiring high-demand tech skills should never put you into crushing debt.\n\n"
            "That's why TekTutors offers the most flexible, learner-first tuition model in the market:\n\n"
            "### 💳 1. Flexible Month-to-Month Tuition:\n"
            "Invest just **₦100,000 / month** as you learn. No lock-in contracts. You can pause or cancel anytime if your schedule changes.\n\n"
            "### 🎁 2. Upfront 10% Cash Rebate (Save ₦10,000):\n"
            "Pay your full tuition upfront and pay just **₦90,000** today (save ₦10,000 immediately at checkout).\n\n"
            "### 🌟 Fast-Action Bonus (Valued at ₦35,000):\n"
            "Enroll this week and unlock a **Free 1-on-1 CV Optimization & LinkedIn Makeover** with our Senior Hiring Consultant to get you noticed by tech recruiters.\n\n"
            "Need assistance selecting your tuition schedule or claiming your discount?\n\n"
            "💬 **[Chat directly with Tara on WhatsApp to claim your bonus]({{tara_chat_url}})**\n\n"
            "Claim your discount and lock in your mentor today:"
        ),
        "cta_text": "Claim Tuition Discount & Enroll",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "day": 3,
        "title": "Market Relevance & High ROI: The Math Behind Your Investment",
        "subject": "The Hiring Math: Why {{course}} Pays for Itself in Under 3 Weeks",
        "body": (
            "Hi {{name}},\n\n"
            "When considering advancing your skills, the most important question is: *\"What is my true return on investment?\"*\n\n"
            "Here is the transparent market reality for data and AI practitioners today:\n\n"
            "### 📊 The Hiring Numbers:\n"
            "• **Junior to Mid Data Analyst (Nigeria):** ₦350,000 – ₦750,000 / month.\n"
            "• **Senior Analyst / BI Lead (Nigeria):** ₦800,000 – ₦1,500,000+ / month.\n"
            "• **Global Remote Roles (UK, US, Canada, EU):** $1,500 – $3,500 / month (₦2,250,000+).\n"
            "• **Payback Period:** Under **3 weeks** of your first month's salary completely covers your entire training investment.\n\n"
            "Companies across banking, fintech, telecom, e-commerce, and logistics are drowning in raw data. They desperately need people who can turn numbers into actionable executive insights.\n\n"
            "By investing in **{{course}}**, you are building recession-proof earning power for the rest of your career.\n\n"
            "Want to calculate your exact career return on investment?\n\n"
            "💬 **[Chat directly with Tara on WhatsApp for personalized salary guidance]({{tara_chat_url}})**"
        ),
        "cta_text": "Invest in High-Income Skills",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "day": 4,
        "title": "Our Competitive Advantages: 3 Employer-Grade Portfolio Projects",
        "subject": "Certificates Don't Get You Hired — These 3 Projects Will ({{course}})",
        "body": (
            "Hi {{name}},\n\n"
            "A certificate of completion looks nice on a wall, but here is what actually convinces hiring managers in interviews:\n\n"
            "**Proof of practical execution.**\n\n"
            "At TekTutors, you graduate with **3 enterprise-grade capstone portfolio projects** hosted directly on your GitHub and LinkedIn:\n\n"
            "1. **Enterprise Data Pipeline & Diagnostic Scoping:** Ingest, clean, and validate messy real-world transaction data using SQL and Python.\n"
            "2. **Interactive Executive C-Suite Dashboard:** Automated KPI dashboard built in Power BI with dynamic DAX metrics, drill-throughs, and mobile layout.\n"
            "3. **Predictive Analytics or Machine Learning Solution:** End-to-end model solving a real business problem (customer churn, sales forecasting, or credit risk).\n\n"
            "When recruiters ask: *\"Can you show me what you've built?\"*, you won't just talk about theory — you will screen-share live, working systems you created 1-on-1 with your mentor.\n\n"
            "Want to preview sample capstones built by our graduates?\n\n"
            "💬 **[Chat directly with Tara on WhatsApp to see live portfolio examples]({{tara_chat_url}})**\n\n"
            "Ready to build an unbeatable tech portfolio?"
        ),
        "cta_text": "Build Your Portfolio with a Mentor",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "day": 5,
        "title": "The Japa Blueprint: Global Remote Roles & Visa Sponsorship",
        "subject": "The Japa Blueprint: How {{course}} Unlocks Global Remote Roles & Visa Sponsorship",
        "body": (
            "Hi {{name}},\n\n"
            "Are you exploring relocation (Japa) or high-yield global remote roles earning in foreign currency ($/£)?\n\n"
            "Here is the reality of foreign tech hiring in the UK, Canada, the US, and Europe:\n"
            "International employers and visa sponsors do not care about paper certificates. What matters is **verified proof of code execution on GitHub and ATS-optimized international positioning.**\n\n"
            "### 🌍 The TekTutors Japa Advantage:\n"
            "• **International ATS CV Optimization:** Formatted for global recruiters and tech visa criteria (UK Global Talent, Canada Tech PR).\n"
            "• **Verified GitHub Commits:** Code reviews by Senior Practitioners ensuring your GitHub looks like an experienced mid-level engineer.\n"
            "• **Foreign Currency Earning Power:** Junior-to-mid global remote roles compensate **$1,500 – $3,500/month (₦2,250,000+)**.\n\n"
            "Learn how our 1-on-1 mentorship equips you with the portfolio and technical interview skills that international recruiters look for.\n\n"
            "💬 **[Chat directly with Tara on WhatsApp to discuss our Japa tech support]({{tara_chat_url}})**\n\n"
            "Take the first step toward your global tech journey today:"
        ),
        "cta_text": "Explore Global Tech Roadmap",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "day": 6,
        "title": "Zero Coding Experience: The Non-Tech Career Switch Blueprint",
        "subject": "Zero Coding Experience? How Finance & Ops Professionals Switch to ₦650k/mo Data Roles",
        "body": (
            "Hi {{name}},\n\n"
            "Are you working in banking, accounting, customer service, operations, or marketing and wondering if you have what it takes to break into tech?\n\n"
            "Here is what top hiring managers know:\n"
            "**You already possess the hardest skill to teach — business commercial acumen.**\n\n"
            "When you combine your commercial intuition with **SQL queries, Power BI interactive reporting, and automated Python workflows**, you become 5x more valuable than a pure computer science graduate with zero business context.\n\n"
            "### 💼 Why Our 1-on-1 Model Succeeds for Beginners:\n"
            "• **Step-by-Step Private Screen Shares:** No jargon, no rushing — your mentor guides you through every tool line by line.\n"
            "• **Real Business Datasets:** Analyze customer churn, branch profitability, and executive KPIs.\n"
            "• **Weekend-Friendly Sessions:** Keep your current job while mastering your new skill set.\n\n"
            "Worried about your background or where to start?\n\n"
            "💬 **[Chat directly with Tara on WhatsApp for a personalized profile assessment]({{tara_chat_url}})**\n\n"
            "Start your confident career transition today:"
        ),
        "cta_text": "Start Your Non-Tech Transition",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "day": 7,
        "title": "Limited Mentor Capacity: Reserving Your Weekend Onboarding Slot",
        "subject": "Final Notice: Your Reserved Mentor Slot is Expiring, {{name}}",
        "body": (
            "Hi {{name}},\n\n"
            "Because our model requires **dedicated 1-on-1 private video mentorship**, our senior mentors can only accept a maximum of 4 new learners per month.\n\n"
            "We have held an onboarding slot for you in **{{course}}** this week, but our admissions system is scheduled to release unconfirmed seats to our waiting list tomorrow morning.\n\n"
            "### Everything Included in Your Onboarding:\n"
            "✅ Live 1-on-1 private mentorship with an active industry practitioner\n"
            "✅ 3 portfolio capstone projects for your resume and LinkedIn\n"
            "✅ Free ₦35,000 1-on-1 CV Optimization & Tech Interview Coaching\n"
            "✅ Flexible ₦100,000/month or ₦90,000 upfront (save ₦10,000)\n\n"
            "Don't let your reserved slot be given away to the waiting list.\n\n"
            "💬 **[Chat directly with Tara on WhatsApp to hold your mentor slot]({{tara_chat_url}})**\n\n"
            "Click below to secure your mentor and confirm your weekend onboarding before your reservation expires:"
        ),
        "cta_text": "Lock In Your Mentor Slot Now",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "day": 9,
        "title": "Inside a Live 1-on-1 Session: Screen Share, Zero Jargon, Real Code",
        "subject": "Behind the Scenes: What a 1-on-1 Screen Share Really Looks Like ({{course}})",
        "body": (
            "Hi {{name}},\n\n"
            "If you've never experienced private technical mentorship, you might be wondering: *\"What actually happens during a 1-on-1 session at TekTutors?\"*\n\n"
            "Here is the exact format:\n\n"
            "### 🖥️ 1. Your Screen is Shared:\n"
            "You don't just sit and watch a passive video lecture. You open your own IDE (VS Code, Power BI Desktop, pgAdmin) and write the code yourself with your mentor.\n\n"
            "### 🔍 2. Real-Time Error Debugging:\n"
            "When a SQL query throws a syntax error or a Python pandas merge behaves unexpectedly, you don't spend 3 days frustrated on StackOverflow. Your mentor spots the issue immediately, explains *why* it failed in simple English, and coaches you to the clean solution.\n\n"
            "### 🎯 3. Commercial Logic & Best Practices:\n"
            "We don't teach abstract textbook puzzles. Every session focuses on how senior engineers in multinational banks, fintechs, and tech startups structure production data.\n\n"
            "Experience the relief and confidence of having a dedicated senior practitioner in your corner.\n\n"
            "💬 **[Chat directly with Tara on WhatsApp to preview how we match you with a mentor]({{tara_chat_url}})**\n\n"
            "Start your private 1-on-1 mentorship journey today:"
        ),
        "cta_text": "Experience 1-on-1 Mentorship",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "day": 11,
        "title": "Capstone Breakdown: Building a ₦50M Customer Churn Pipeline",
        "subject": "How Our Students Build ₦50M Business Intelligence Systems ({{course}})",
        "body": (
            "Hi {{name}},\n\n"
            "When you apply for a high-paying Data or AI role, hiring managers will ask one question:\n\n"
            "**\"What is the most impactful project you've built from scratch?\"**\n\n"
            "Here is what TekTutors graduates present in technical interviews:\n\n"
            "### 📊 Project Showcase: Enterprise Customer Churn Diagnostic\n"
            "• **Business Problem:** A subscription company losing ₦50,000,000 annually to customer churn.\n"
            "• **SQL Data Pipeline:** Aggregated 250,000 customer transaction records, segmented customer cohorts, and isolated drop-off touchpoints.\n"
            "• **Power BI Executive Dashboard:** Built dynamic churn risk filters, DAX customer lifetime value (CLV) indicators, and automated email trigger alerts.\n"
            "• **Actionable C-Suite Impact:** Pinpointed a 14% retention improvement that saved the business ₦18,000,000 in lost revenue.\n\n"
            "When recruiters see this on your GitHub and LinkedIn, you immediately stand out from candidates who only have generic tutorial certificates.\n\n"
            "💬 **[Chat directly with Tara on WhatsApp to explore our project capstone library]({{tara_chat_url}})**\n\n"
            "Build portfolio projects that get you hired:"
        ),
        "cta_text": "Build Enterprise Portfolio Projects",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "day": 13,
        "title": "Defeating Imposter Syndrome: You Don't Need to Be a Math Genius",
        "subject": "Scared of Math or Coding? Read This Before Giving Up ({{course}})",
        "body": (
            "Hi {{name}},\n\n"
            "One of the most common secrets our incoming students confess to Tara is:\n\n"
            "*\"I really want to get into tech, but I was never good at math, and code feels intimidating.\"*\n\n"
            "Here is the truth:\n"
            "Modern Data Analytics and Business Intelligence is **not** about complex calculus or theoretical algorithms.\n\n"
            "### 💡 What Data Analytics Actually Requires:\n"
            "1. **Curiosity:** Asking why sales dropped in July, or which marketing channel delivered the best leads.\n"
            "2. **Pattern Recognition:** Looking at trends, averages, and percentages.\n"
            "3. **Clear Communication:** Explaining your findings to stakeholders who don't know code.\n\n"
            "The technical tools (SQL, Power BI, Python) are just tools — and with a patient 1-on-1 mentor guiding you step-by-step, you'll be writing clean queries in your very first week.\n\n"
            "Don't let self-doubt rob you of a lucrative career in tech.\n\n"
            "💬 **[Chat directly with Tara on WhatsApp for a quick encouragement & skill evaluation]({{tara_chat_url}})**\n\n"
            "Take the leap with a dedicated mentor today:"
        ),
        "cta_text": "Start Fearlessly with a Mentor",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "day": 15,
        "title": "The Recruiter Magnet: How TekTutors Students Get Inbound Interview Invites",
        "subject": "The Recruiter Magnet: How TekTutors Students Get Inbound Interview Invites",
        "body": (
            "Hi {{name}},\n\n"
            "Most job seekers spend hours submitting resumes into online application portals, only to receive silence.\n\n"
            "At TekTutors, we teach our students how to become **Recruiter Magnets** on LinkedIn:\n\n"
            "### 🧲 The Inbound Positioning Strategy:\n"
            "• **ATS-Optimized Headline:** Transforming generic titles into searchable practitioner keywords (e.g. *\"Data Analyst | SQL | Power BI | Financial Performance Modelling\"*).\n"
            "• **Live Project Embeds:** Video walkthroughs of your interactive Power BI dashboards pinned directly to the Featured section of your profile.\n"
            "• **Verified GitHub Commits:** A green GitHub activity board that proves hands-on code consistency.\n\n"
            "Every TekTutors student receives our **Free ₦35,000 LinkedIn & CV Makeover** so international recruiters from the UK, Canada, and Nigeria find you directly.\n\n"
            "💬 **[Chat directly with Tara on WhatsApp to claim your Free LinkedIn Makeover bonus]({{tara_chat_url}})**\n\n"
            "Position yourself for high-paying inbound tech roles:"
        ),
        "cta_text": "Claim Your Free LinkedIn Makeover",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "day": 17,
        "title": "Earning in Foreign Currency While Learning: The Freelance Roadmap",
        "subject": "How to Land Your First $300 – $500 Data Gig While Still Training ({{course}})",
        "body": (
            "Hi {{name}},\n\n"
            "Did you know that many TekTutors students start earning freelance income before they even graduate?\n\n"
            "International small businesses and agencies on platforms like Upwork, Fiverr, and Contra frequently need quick data cleanups, dashboard builds, and Excel automations:\n\n"
            "### 💵 High-Demand Micro-Gigs for Beginners:\n"
            "• Cleaning and deduplicating messy CRM spreadsheets: **$150 – $300**\n"
            "• Building a custom 3-page interactive Power BI dashboard: **$350 – $700**\n"
            "• Writing SQL queries to extract monthly financial reports: **$250 – $500**\n\n"
            "With exchange rates, landing just one $400 project brings in over **₦600,000** — more than covering your entire tuition!\n\n"
            "Your mentor will guide you on how to package your training capstones into marketable client deliverables.\n\n"
            "💬 **[Chat directly with Tara on WhatsApp to discuss remote freelance earning]({{tara_chat_url}})**\n\n"
            "Start building international earning power today:"
        ),
        "cta_text": "Learn to Earn in Dollars",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "day": 20,
        "title": "The True Cost of Waiting: Where Will Your Career Be in 6 Months?",
        "subject": "The ₦1,200,000 Cost of Waiting Another Month, {{name}}",
        "body": (
            "Hi {{name}},\n\n"
            "We all have career goals we promise ourselves we will start *\"next month\"*.\n\n"
            "But let's look at the real financial math of delaying your tech transition:\n\n"
            "If you start **{{course}}** today, in just 8 weeks you will have:\n"
            "✅ 3 completed enterprise portfolio capstones on GitHub\n"
            "✅ Fluency in SQL queries, Power BI reporting, and business analytics\n"
            "✅ An optimized resume ready for roles paying ₦450k – ₦850k/month locally or $1.5k–$3.5k remotely\n\n"
            "Every month you delay is another month working at your current income level while inflation rises.\n\n"
            "Make this month the turning point where you invest in yourself.\n\n"
            "💬 **[Chat directly with Tara on WhatsApp to structure your learning schedule]({{tara_chat_url}})**\n\n"
            "Take control of your earning trajectory today:"
        ),
        "cta_text": "Invest in Your Career Trajectory",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "day": 22,
        "title": "Special Admissions Grant: ₦15,000 Fast-Track Scholarship",
        "subject": "Exclusive Admissions Grant: ₦15,000 Tuition Voucher (48 Hours Only)",
        "body": (
            "Hi {{name}},\n\n"
            "Great news for your tech journey!\n\n"
            "The TekTutors Academic Board has approved a limited **₦15,000 Fast-Track Tuition Grant** for prospective students ready to onboard with a mentor this week.\n\n"
            "### 🎟️ Your Grant Details:\n"
            "• **Standard Full Tuition:** ₦100,000\n"
            "• **Fast-Track Grant Applied:** -₦15,000\n"
            "• **Your Special Tuition:** **₦85,000 only** (or split into two payments of ₦45,000)\n"
            "• **Includes:** Dedicated 1-on-1 live screen share mentorship, 3 GitHub capstones, and free ₦35k CV optimization.\n\n"
            "This voucher expires in **48 hours** as mentor seats are strictly capped.\n\n"
            "💬 **[Chat directly with Tara on WhatsApp to apply your ₦15,000 grant voucher]({{tara_chat_url}})**\n\n"
            "Claim your tuition grant before it expires:"
        ),
        "cta_text": "Claim ₦15,000 Tuition Grant",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "day": 25,
        "title": "From ₦85k Customer Support to ₦650k Business Intelligence Specialist",
        "subject": "Meet Femi: From ₦85k Customer Care to ₦650k Data Lead in 4 Months",
        "body": (
            "Hi {{name}},\n\n"
            "Meet Femi — four months ago, he was working long hours in customer service earning ₦85,000/month, wondering how to break into tech without a computer science degree.\n\n"
            "### 🚀 How Femi Made the Leap with TekTutors:\n"
            "1. **Weekend 1-on-1 Sessions:** He kept his day job and dedicated Saturday & Sunday mornings to private screen shares with his senior mentor.\n"
            "2. **Built Real Telemetry Capstones:** Instead of watching passive videos, he built an executive sales performance dashboard using SQL and Power BI.\n"
            "3. **Mock Technical Interviews:** His mentor drilled him on actual corporate interview scenarios until he could answer questions with authority.\n\n"
            "Last month, Femi accepted an offer as a **Business Intelligence Specialist at a Lagos fintech firm earning ₦650,000/month**.\n\n"
            "His story is not unique — it is the exact blueprint we guide our students through every day.\n\n"
            "💬 **[Chat directly with Tara on WhatsApp to read more student success stories]({{tara_chat_url}})**\n\n"
            "Start writing your own tech success story:"
        ),
        "cta_text": "Start Your Tech Success Story",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "day": 28,
        "title": "Getting Ready for Day 1: Zero Setup Friction",
        "subject": "Your Laptop Setup & 1-on-1 Schedule Checklist ({{course}})",
        "body": (
            "Hi {{name}},\n\n"
            "Worried about technical setup or installing complex software?\n\n"
            "At TekTutors, we make onboarding completely frictionless.\n\n"
            "### 💻 What You Need for Your First Session:\n"
            "• Any standard laptop (Windows or Mac, 8GB RAM recommended)\n"
            "• Stable internet connection for screen sharing\n"
            "• That's it! Zero pre-installation needed.\n\n"
            "During your first private session, your mentor will screen-share with you and assist you in setting up Python, PostgreSQL, and Power BI step-by-step.\n\n"
            "You won't have to troubleshoot installations alone.\n\n"
            "💬 **[Chat directly with Tara on WhatsApp to confirm your laptop compatibility]({{tara_chat_url}})**\n\n"
            "Get paired with your mentor this weekend:"
        ),
        "cta_text": "Get Paired with Your Mentor",
        "cta_url": "https://tektutors.com.ng/registration"
    },
    {
        "day": 30,
        "title": "Final Admissions Call: Securing Your 1-on-1 Mentor Pairing This Month",
        "subject": "Final Notice: Your Reserved Mentor Pairing is Closing Today, {{name}}",
        "body": (
            "Hi {{name}},\n\n"
            "This is our final notification regarding your admissions reservation for **{{course}}**.\n\n"
            "Our mentors are locking in their student pairing schedules for the upcoming cohort this evening. Because each practitioner can only coach **4 learners at a time**, unconfirmed slots will be released to prospective candidates on our waiting list.\n\n"
            "### 🌟 Everything Waiting for You:\n"
            "✅ 1-on-1 private screen share sessions with an active senior engineer\n"
            "✅ 3 high-impact portfolio capstones deployed to GitHub\n"
            "✅ Free ₦35,000 CV Optimization & LinkedIn Makeover\n"
            "✅ Flexible ₦100,000/month or ₦90,000 upfront (save ₦10,000)\n\n"
            "Don't spend another month wondering *\"what if\"*.\n\n"
            "💬 **[Chat directly with Tara on WhatsApp right now to secure your mentor slot]({{tara_chat_url}})**\n\n"
            "Lock in your mentor and start your career upgrade today:"
        ),
        "cta_text": "Lock In Your Mentor Slot Before It Closes",
        "cta_url": "https://tektutors.com.ng/registration"
    }
]


def get_nurture_sequence_for_duration(duration_days: int = 30, cadence: str = "smart_spaced") -> List[Dict[str, Any]]:
    """
    Intelligently construct a high-converting nurture campaign spanning a requested duration (e.g. 7, 14, 30 days, or custom).
    Supports multiple delivery cadences:
    - 'smart_spaced': Psychologically spaced across the duration (e.g. Days 1, 2, 4, 7, 9, 11, 13, 15, 17, 20, 22, 25, 28, 30).
    - 'daily': Sends an email every single day up to duration_days.
    - 'alternate': Sends an email every 2 days (Day 1, 3, 5, 7, 9...) up to duration_days.
    - 'weekly': Sends an email once a week (Day 1, 8, 15, 22, 29...) up to duration_days.
    """
    duration = max(1, int(duration_days or 30))
    cadence = (cadence or "smart_spaced").lower().strip()

    # Pre-crafted optimal day-mappings for standard durations
    if duration == 7:
        target_days = [1, 2, 3, 4, 5, 6, 7]
    elif duration == 14 and cadence == "smart_spaced":
        target_days = [1, 2, 4, 6, 8, 11, 14]
    elif duration == 30 and cadence == "smart_spaced":
        target_days = [1, 2, 4, 7, 9, 11, 13, 15, 17, 20, 22, 25, 28, 30]
    elif cadence == "daily":
        target_days = list(range(1, duration + 1))
    elif cadence == "alternate":
        target_days = list(range(1, duration + 1, 2))
        if target_days[-1] != duration and duration > 1:
            target_days.append(duration)
    elif cadence == "weekly":
        target_days = list(range(1, duration + 1, 7))
        if target_days[-1] != duration and duration > 3:
            target_days.append(duration)
    else:
        # Default smart spacing: map up to 14 touchpoints proportionally across the duration
        num_touches = min(14, max(3, duration // 2))
        if num_touches >= duration:
            target_days = list(range(1, duration + 1))
        else:
            step = (duration - 1) / (num_touches - 1)
            raw_days = [round(1 + i * step) for i in range(num_touches)]
            target_days = sorted(list(set(raw_days)))

    # Match each target day with the most appropriate template from DAILY_DRIP_SEQUENCE
    built_sequence = []
    pool = DAILY_DRIP_SEQUENCE

    for idx, day_num in enumerate(target_days):
        # Pick template from pool (cycling or matching closest day)
        if idx == 0:
            tpl = pool[0]  # Welcome & Curriculum Roadmap
        elif idx == len(target_days) - 1:
            tpl = pool[-1]  # Final Admissions Urgency / Reserved Mentor Pairing
        elif idx < len(pool) - 1:
            tpl = pool[idx]
        else:
            tpl = pool[idx % (len(pool) - 1)]

        item = dict(tpl)
        item["day"] = day_num
        item["step_index"] = idx + 1
        item["total_steps"] = len(target_days)
        built_sequence.append(item)

    return built_sequence



def parse_schedule_time(delay_or_time_str: str) -> datetime.datetime:
    """
    Parse a user or API time string into a concrete future datetime.
    Supports relative offsets ('in 2 hours', 'tomorrow', '24h', '3 days')
    as well as ISO timestamps ('2026-09-19T10:00:00').
    """
    now = datetime.datetime.now()
    if not delay_or_time_str or not isinstance(delay_or_time_str, str):
        return now + datetime.timedelta(hours=24)

    clean_str = delay_or_time_str.strip().lower()

    # Relative shortcuts
    if "tomorrow morning" in clean_str:
        tomorrow = now + datetime.timedelta(days=1)
        return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
    elif "tomorrow evening" in clean_str:
        tomorrow = now + datetime.timedelta(days=1)
        return tomorrow.replace(hour=18, minute=0, second=0, microsecond=0)
    elif "tomorrow" in clean_str or "next day" in clean_str:
        tomorrow = now + datetime.timedelta(days=1)
        return tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)

    # Regex for relative hours: 'in 2 hours', '2 hrs', '2h'
    hour_match = re.search(r'(\d+)\s*(?:hour|hr|h)', clean_str)
    if hour_match:
        hours = int(hour_match.group(1))
        return now + datetime.timedelta(hours=hours)

    # Regex for relative days: 'in 3 days', '3d', '3 days'
    day_match = re.search(r'(\d+)\s*(?:day|d)', clean_str)
    if day_match:
        days = int(day_match.group(1))
        return now + datetime.timedelta(days=days)

    # Regex for relative minutes: 'in 30 mins', '30m'
    min_match = re.search(r'(\d+)\s*(?:minute|min|m)', clean_str)
    if min_match:
        mins = int(min_match.group(1))
        return now + datetime.timedelta(minutes=mins)

    # Try ISO parsing
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(delay_or_time_str.strip(), fmt)
        except ValueError:
            continue

    # Default fallback to 24 hours
    return now + datetime.timedelta(hours=24)


async def schedule_email_async(
    to_email: str,
    subject: str,
    body_markdown: str,
    scheduled_for: datetime.datetime,
    to_name: Optional[str] = "Student",
    campaign_type: str = "scheduled_followup",
    lead_id: Optional[int] = None,
    course_name: Optional[str] = "Data Analytics & BI Accelerator",
    cta_text: str = "Register Online",
    cta_url: str = "https://tektutors.com.ng/registration",
    sequence_day: int = 0
) -> Dict[str, Any]:
    """Persist a future email into the ScheduledEmail queue."""
    clean_email = to_email.strip().lower()
    clean_name = to_name.strip() if to_name else "Student"

    async with AsyncSessionLocal() as db:
        scheduled_rec = ScheduledEmail(
            lead_id=lead_id,
            recipient_email=clean_email,
            recipient_name=clean_name,
            sequence_day=sequence_day,
            subject=subject,
            body_markdown=body_markdown,
            campaign_type=campaign_type,
            course_name=course_name,
            cta_text=cta_text,
            cta_url=cta_url,
            scheduled_for=scheduled_for,
            status="pending"
        )
        db.add(scheduled_rec)
        await db.commit()
        await db.refresh(scheduled_rec)

    logger.info(f"Queued scheduled email #{scheduled_rec.id} for {clean_email} at {scheduled_for} (Subject: {subject})")
    return {
        "scheduled_id": scheduled_rec.id,
        "recipient_email": clean_email,
        "recipient_name": clean_name,
        "subject": subject,
        "scheduled_for": scheduled_for.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "pending",
        "sequence_day": sequence_day
    }


async def enroll_lead_in_daily_drip_sequence(
    lead_id: Optional[int],
    email: str,
    name: Optional[str] = "Student",
    course_name: Optional[str] = "Data Analytics & BI Accelerator",
    drip_days: Optional[int] = 30,
    cadence: Optional[str] = "smart_spaced",
    start_time: Optional[Any] = "tomorrow_morning"
) -> Dict[str, Any]:
    """
    Enroll a prospective student into the intelligent multi-day / 1-month nurture sequence.
    Schedules future emails across the chosen period (e.g. 7, 14, 30 days, or custom) in ScheduledEmail.
    Every email is strategically crafted around 1-on-1 mentorship, TekTutors offers, Japa support,
    real portfolio capstones, and includes direct personalized links to chat with Tara on WhatsApp.
    """
    clean_email = email.strip().lower()
    clean_name = name.strip() if name and name.lower() not in ("prospect", "student", "") else "Student"
    target_course = course_name or "Data Analytics & BI Accelerator"
    now = datetime.datetime.now()

    # Guard against duplicate active drip enrollments for the same lead/email
    async with AsyncSessionLocal() as db:
        stmt = select(ScheduledEmail).where(
            ScheduledEmail.recipient_email == clean_email,
            ScheduledEmail.status == "pending",
            ScheduledEmail.campaign_type.in_(("daily_drip_nurture", "month_long_nurture", "custom_drip_nurture"))
        )
        res = await db.execute(stmt)
        existing = res.scalars().all()
        if existing:
            logger.info(f"Lead {clean_email} already has {len(existing)} pending drip emails queued. Skipping re-enrollment.")
            return {
                "status": "already_enrolled",
                "pending_count": len(existing),
                "recipient_email": clean_email
            }

    target_drip_days = drip_days if drip_days is not None else 30
    sequence_items = get_nurture_sequence_for_duration(duration_days=target_drip_days, cadence=cadence or "smart_spaced")
    scheduled_records = []

    # Calculate starting delivery anchor
    start_str = str(start_time or "tomorrow_morning").lower().strip()
    is_immediate = start_str in ("immediate", "now", "0")

    if not is_immediate and start_str not in ("tomorrow_morning", "tomorrow", ""):
        try:
            base_anchor = parse_schedule_time(start_str)
        except Exception:
            base_anchor = now + datetime.timedelta(days=1)
    else:
        base_anchor = now + datetime.timedelta(days=1)

    base_anchor = base_anchor.replace(hour=10, minute=0, second=0, microsecond=0)

    # Schedule sequence days
    for item in sequence_items:
        day_num = item["day"]
        if is_immediate and day_num == 1:
            delivery_time = now + datetime.timedelta(minutes=5)
        else:
            delivery_time = base_anchor + datetime.timedelta(days=day_num - 1)

        # Personalize subject & body
        enc_c = urllib.parse.quote(target_course)
        enc_n = urllib.parse.quote(clean_name)
        step_tara_url = f"https://wa.me/2349112120531?text=Hi%20Tara%2C%20I%20am%20{enc_n}.%20I%20got%20your%20email%20about%20{enc_c}%20and%20I%20want%20to%20learn%20with%20TekTutors."
        p_subject = item["subject"].replace("{{name}}", clean_name).replace("{{course}}", target_course)
        p_body = item["body"].replace("{{name}}", clean_name).replace("{{course}}", target_course).replace("{{tara_chat_url}}", step_tara_url)

        rec = await schedule_email_async(
            to_email=clean_email,
            subject=p_subject,
            body_markdown=p_body,
            scheduled_for=delivery_time,
            to_name=clean_name,
            campaign_type="daily_drip_nurture" if target_drip_days <= 7 else "month_long_nurture",
            lead_id=lead_id,
            course_name=target_course,
            cta_text=item.get("cta_text", "Register Online"),
            cta_url=item.get("cta_url", "https://tektutors.com.ng/registration"),
            sequence_day=day_num
        )
        scheduled_records.append(rec)

    logger.info(f"Successfully enrolled {clean_email} into {len(scheduled_records)}-touch nurture sequence spanning {target_drip_days} days.")
    return {
        "status": "enrolled",
        "recipient_email": clean_email,
        "course": target_course,
        "duration_days": target_drip_days,
        "cadence": cadence or "smart_spaced",
        "scheduled_emails_count": len(scheduled_records),
        "schedule": scheduled_records
    }


def parse_campaign_csv_data(csv_text_or_bytes: Any, filename: Optional[str] = None) -> Dict[str, Any]:
    """
    Intelligently parse external CSV / TSV / Excel (.xlsx) / text data for email campaigns.
    Handles multiple delimiters (comma, semicolon, tab, pipe), BOM encodings, Excel worksheets,
    fuzzy column header recognition (email, name, course, phone, notes),
    email validation, deduplication, and synthetic phone generation for CRM.
    """
    import csv
    import io
    import re

    all_rows = []

    # 1. Check for Excel spreadsheet (.xlsx, .xlsm, .xltx or PK zip signature)
    is_excel = False
    if filename and filename.lower().endswith(('.xlsx', '.xlsm', '.xltx')):
        is_excel = True
    elif isinstance(csv_text_or_bytes, bytes) and csv_text_or_bytes.startswith(b'PK\x03\x04'):
        is_excel = True

    if is_excel and isinstance(csv_text_or_bytes, bytes):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(csv_text_or_bytes), read_only=True, data_only=True)
            sheet = wb.active
            for row in sheet.iter_rows(values_only=True):
                str_row = [str(c).strip() if c is not None else "" for c in row]
                if any(str_row):
                    all_rows.append(str_row)
        except Exception as e:
            logger.warning(f"Error parsing Excel workbook with openpyxl: {e}. Falling back to text decoding.")

    # 2. Text / CSV / TSV fallback parsing
    if not all_rows:
        if isinstance(csv_text_or_bytes, bytes):
            try:
                raw_text = csv_text_or_bytes.decode('utf-8-sig')
            except UnicodeDecodeError:
                raw_text = csv_text_or_bytes.decode('latin-1', errors='ignore')
        else:
            raw_text = str(csv_text_or_bytes or '')

        raw_text = raw_text.replace('\ufeff', '').strip()
        if not raw_text:
            return {
                "total_rows": 0,
                "valid_count": 0,
                "invalid_count": 0,
                "columns_detected": {},
                "valid_recipients": [],
                "invalid_recipients": [],
                "preview": []
            }

        # Detect delimiter with fallback
        sample = raw_text[:2048]
        delimiter = ','
        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(sample, delimiters=',;\t|')
            delimiter = dialect.delimiter
        except Exception:
            for d in [',', ';', '\t', '|']:
                if d in sample:
                    delimiter = d
                    break

        reader = csv.reader(io.StringIO(raw_text), delimiter=delimiter)
        all_rows = [r for r in reader if any(field.strip() for field in r)]
    if not all_rows:
        return {
            "total_rows": 0,
            "valid_count": 0,
            "invalid_count": 0,
            "columns_detected": {},
            "valid_recipients": [],
            "invalid_recipients": [],
            "preview": []
        }

    headers = [h.strip() for h in all_rows[0]]
    # Robust Header Detection: Google Forms / CRM exports often have multiple descriptive headers.
    # Check if row 0 contains 2 or more standard header tokens.
    header_hits = 0
    for h in headers:
        clean_token = re.sub(r'[^a-zA-Z0-9]', '', h.lower())
        if any(k in clean_token for k in ('email', 'mail', 'name', 'phone', 'course', 'track', 'program', 'time', 'timestamp', 'date', 'qualif', 'skill', 'discipline', 'address', 'comment', 'suggestion')):
            header_hits += 1

    has_header = header_hits >= 2
    data_rows = all_rows[1:] if has_header else all_rows

    col_map = {}
    if has_header:
        for idx, h in enumerate(headers):
            hl = h.lower()
            clean_h = re.sub(r'[^a-zA-Z0-9]', '', hl)

            # 1. Email detection (prioritize 'email address' or 'email')
            if 'email' in clean_h or 'mail' in clean_h:
                if 'email' not in col_map or 'address' in clean_h:
                    col_map['email'] = idx

            # 2. Name detection (has 'name' but NOT 'course', 'account', 'bank', etc.)
            if 'name' in clean_h and not any(k in clean_h for k in ('course', 'account', 'bank', 'school', 'company', 'program')):
                if 'name' not in col_map or 'full' in clean_h:
                    col_map['name'] = idx

            # 3. Course / Track detection
            if any(k in clean_h for k in ('course', 'track', 'program', 'training', 'discipline')):
                if 'course' not in col_map or 'prefer' in clean_h:
                    col_map['course'] = idx

            # 4. Phone detection
            if any(k in clean_h for k in ('phone', 'mobile', 'whatsapp', 'tel', 'cell')):
                if 'phone' not in col_map:
                    col_map['phone'] = idx

            # 5. Notes / Qualifications / Remarks detection
            if any(k in clean_h for k in ('comment', 'suggestion', 'note', 'remark', 'qualification', 'skills')):
                if 'notes' not in col_map:
                    col_map['notes'] = idx

    # If email column not found by header, auto-detect column containing '@' across data rows
    if 'email' not in col_map and data_rows:
        best_col = None
        max_at_count = 0
        num_cols = max(len(r) for r in data_rows[:20])
        for col_idx in range(num_cols):
            at_count = sum(1 for r in data_rows if len(r) > col_idx and '@' in r[col_idx])
            if at_count > max_at_count:
                max_at_count = at_count
                best_col = col_idx
        if best_col is not None and max_at_count > 0:
            col_map['email'] = best_col

    # Default name to column 0 or 1 if not email
    if 'name' not in col_map and data_rows:
        for idx in range(min(3, len(data_rows[0]))):
            if idx != col_map.get('email'):
                col_map['name'] = idx
                break

    # Default course to another text column if present
    if 'course' not in col_map and data_rows and len(data_rows[0]) > 2:
        for idx in range(len(data_rows[0])):
            if idx != col_map.get('email') and idx != col_map.get('name') and idx != col_map.get('phone'):
                col_map['course'] = idx
                break

    valid_recipients = []
    invalid_recipients = []
    seen_emails = set()

    for row_idx, row in enumerate(data_rows, start=1):
        if not row or not any(field.strip() for field in row):
            continue

        raw_email = ""
        # Check mapped email index first
        if 'email' in col_map and len(row) > col_map['email']:
            candidate = row[col_map['email']].strip().lower()
            if re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', candidate):
                raw_email = candidate

        # If primary email column didn't have a valid email, scan other columns for valid email fallback
        if not raw_email:
            for c_val in row:
                candidate = c_val.strip().lower()
                if re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', candidate):
                    raw_email = candidate
                    break

        # Validate email
        if not raw_email:
            invalid_recipients.append({
                "row": row_idx,
                "raw": row,
                "reason": "Invalid or missing email address"
            })
            continue

        if raw_email in seen_emails:
            invalid_recipients.append({
                "row": row_idx,
                "raw": row,
                "reason": f"Duplicate email address '{raw_email}'"
            })
            continue

        seen_emails.add(raw_email)

        # Extract name
        raw_name = ""
        if 'name' in col_map and len(row) > col_map['name']:
            raw_name = row[col_map['name']].strip()
        if not raw_name:
            # Derive friendly name from email username (e.g. alex.smith -> Alex Smith)
            username = raw_email.split('@')[0]
            clean_derived = re.sub(r'[\._\-+0-9]+', ' ', username).strip().title()
            raw_name = clean_derived if clean_derived else "Student"

        # Extract course
        raw_course = ""
        if 'course' in col_map and len(row) > col_map['course']:
            raw_c = row[col_map['course']].strip()
            if raw_c:
                # If multiple courses selected (e.g. "Power BI, SQL, Excel"), select the primary choice
                c_split = [item.strip() for item in raw_c.split(',') if item.strip()]
                raw_course = c_split[0] if c_split else raw_c
        if not raw_course:
            raw_course = "Data Analytics & BI Accelerator"

        # Extract phone (auto-format Nigerian numbers if applicable)
        raw_phone = ""
        if 'phone' in col_map and len(row) > col_map['phone']:
            clean_p = re.sub(r'[^0-9+]', '', row[col_map['phone']].strip())
            if clean_p.startswith('0') and len(clean_p) == 11:
                raw_phone = '+234' + clean_p[1:]
            else:
                raw_phone = clean_p

        # Extract notes
        raw_notes = ""
        if 'notes' in col_map and len(row) > col_map['notes']:
            raw_notes = row[col_map['notes']].strip()

        valid_recipients.append({
            "email": raw_email,
            "name": raw_name,
            "course": raw_course,
            "phone": raw_phone,
            "notes": raw_notes
        })

    # Prepare readable column detected mapping
    readable_cols = {}
    for col_key, col_idx in col_map.items():
        if has_header and col_idx < len(headers):
            readable_cols[col_key] = headers[col_idx]
        else:
            readable_cols[col_key] = f"Col {col_idx}"

    return {
        "total_rows": len(data_rows),
        "valid_count": len(valid_recipients),
        "invalid_count": len(invalid_recipients),
        "columns_detected": readable_cols,
        "valid_recipients": valid_recipients,
        "invalid_recipients": invalid_recipients,
        "preview": valid_recipients[:25]
    }


async def process_due_scheduled_emails() -> List[Dict[str, Any]]:
    """
    Periodic job worker: fetch and dispatch all pending emails whose scheduled_for <= now.
    """
    now = datetime.datetime.now()
    due_records = []

    async with AsyncSessionLocal() as db:
        stmt = select(ScheduledEmail).where(
            ScheduledEmail.status == "pending",
            ScheduledEmail.scheduled_for <= now
        ).order_by(ScheduledEmail.scheduled_for.asc()).limit(20)
        res = await db.execute(stmt)
        due_records = res.scalars().all()

    if not due_records:
        return []

    logger.info(f"Processing {len(due_records)} due scheduled email(s)...")
    results = []

    for item in due_records:
        # Check if parent lead enrolled in the meantime; if so, cancel drip
        should_skip = False
        if item.lead_id:
            async with AsyncSessionLocal() as db:
                l_res = await db.execute(select(Lead).where(Lead.id == item.lead_id))
                lead = l_res.scalar_one_or_none()
                if lead and lead.status == "enrolled":
                    should_skip = True

        if should_skip:
            async with AsyncSessionLocal() as db:
                rec_stmt = select(ScheduledEmail).where(ScheduledEmail.id == item.id)
                rec = (await db.execute(rec_stmt)).scalar_one_or_none()
                if rec:
                    rec.status = "cancelled"
                    rec.error_message = "Lead already enrolled; remaining drip cancelled."
                    await db.commit()
            results.append({"id": item.id, "status": "cancelled", "reason": "already_enrolled"})
            continue

        # Send email via core engine
        send_res = await send_email_async(
            recipient_email=item.recipient_email,
            recipient_name=item.recipient_name,
            subject=item.subject,
            body_markdown=item.body_markdown,
            campaign_type=item.campaign_type,
            lead_id=item.lead_id,
            cta_text=item.cta_text or "Register Online",
            cta_url=item.cta_url or "https://tektutors.com.ng/registration",
            course_name=item.course_name or "Data Analytics & BI Accelerator"
        )

        new_status = send_res.get("status", "failed")
        async with AsyncSessionLocal() as db:
            rec_stmt = select(ScheduledEmail).where(ScheduledEmail.id == item.id)
            rec = (await db.execute(rec_stmt)).scalar_one_or_none()
            if rec:
                rec.status = new_status
                rec.sent_at = datetime.datetime.now()
                rec.error_message = send_res.get("error_message")
                await db.commit()

        results.append({
            "id": item.id,
            "recipient_email": item.recipient_email,
            "subject": item.subject,
            "status": new_status,
            "error": send_res.get("error_message")
        })

    return results


async def cancel_scheduled_email(scheduled_id: int) -> bool:
    """Cancel a pending scheduled email."""
    async with AsyncSessionLocal() as db:
        stmt = select(ScheduledEmail).where(ScheduledEmail.id == scheduled_id)
        res = await db.execute(stmt)
        item = res.scalar_one_or_none()
        if item and item.status == "pending":
            item.status = "cancelled"
            await db.commit()
            return True
        return False


async def cancel_scheduled_emails_for_lead(lead_id: int) -> int:
    """Cancel all future pending scheduled emails for a lead."""
    async with AsyncSessionLocal() as db:
        stmt = select(ScheduledEmail).where(
            ScheduledEmail.lead_id == lead_id,
            ScheduledEmail.status == "pending"
        )
        res = await db.execute(stmt)
        items = res.scalars().all()
        for it in items:
            it.status = "cancelled"
        await db.commit()
        return len(items)


# Background Worker Task
_worker_task: Optional[asyncio.Task] = None
_worker_running: bool = False

async def _scheduled_email_worker_loop():
    logger.info("📅 Scheduled Email Background Dispatcher started (Polling every 30s)...")
    while _worker_running:
        try:
            await process_due_scheduled_emails()
        except Exception as e:
            logger.error(f"Error in scheduled email worker loop: {e}")
        try:
            await asyncio.sleep(30)
        except (asyncio.CancelledError, GeneratorExit):
            break

def start_scheduled_email_worker():
    global _worker_task, _worker_running
    import sys
    if os.getenv("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return
    if not _worker_running:
        _worker_running = True
        _worker_task = asyncio.create_task(_scheduled_email_worker_loop())

def stop_scheduled_email_worker():
    global _worker_task, _worker_running
    _worker_running = False
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()


