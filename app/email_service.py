import os
import re
import smtplib
import asyncio
import logging
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any, List
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import EmailLog, Lead

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
    }
]

def render_branded_email_html(
    subject: str,
    body_markdown: str,
    cta_text: str = "Register Online",
    cta_url: str = "https://tektutors.com.ng/registration",
    recipient_name: str = "Student"
) -> str:
    """Render modern, responsive HTML email matching TekTutors visual identity."""
    paragraphs = [p.strip() for p in body_markdown.split("\n\n") if p.strip()]
    formatted_paras = []
    
    for p in paragraphs:
        if any(p.startswith(prefix) for prefix in ["•", "-", "✅", "1.", "2.", "3."]):
            lines = p.split("\n")
            items = []
            for line in lines:
                clean_line = re.sub(r'^[•\-\*✅\d\.]+\s*', '', line.strip())
                clean_line = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', clean_line)
                items.append(f'<li style="margin-bottom: 8px; line-height: 1.6;">{clean_line}</li>')
            formatted_paras.append(f'<ul style="padding-left: 20px; color: #334155; margin: 16px 0;">{"".join(items)}</ul>')
        else:
            p_html = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', p)
            p_html = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', p_html)
            p_html = p_html.replace("\n", "<br>")
            formatted_paras.append(f'<p style="margin: 0 0 16px 0; line-height: 1.65; color: #334155; font-size: 15px;">{p_html}</p>')

    body_content_html = "\n".join(formatted_paras)

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
          
          <!-- Header Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 32px 28px; text-align: left; border-bottom: 3px solid #eb6711;">
              <table width="100%" role="presentation">
                <tr>
                  <td>
                    <div style="font-size: 22px; font-weight: 800; color: #ffffff; letter-spacing: -0.5px;">
                      Tek<span style="color: #eb6711;">Tutors</span>
                    </div>
                    <div style="font-size: 12px; color: #94a3b8; margin-top: 4px; font-weight: 500;">
                      Practical Data Analytics & AI Mentorship Academy
                    </div>
                  </td>
                  <td align="right">
                    <span style="display: inline-block; padding: 4px 10px; background: rgba(235, 103, 17, 0.18); border: 1px solid rgba(235, 103, 17, 0.4); color: #ff8c3a; font-size: 11px; font-weight: 700; border-radius: 20px; text-transform: uppercase; letter-spacing: 0.5px;">
                      Live 1-on-1 Mentorship
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Email Content Body -->
          <tr>
            <td style="padding: 36px 32px 28px 32px;">
              <h1 style="margin: 0 0 20px 0; font-size: 20px; font-weight: 700; color: #0f172a; line-height: 1.35;">
                {subject}
              </h1>

              {body_content_html}

              <!-- Primary CTA Button -->
              <table role="presentation" cellspacing="0" cellpadding="0" style="margin: 32px 0 24px 0;">
                <tr>
                  <td align="left" style="border-radius: 8px; background: #eb6711;">
                    <a href="{cta_url}" target="_blank" style="display: inline-block; padding: 14px 28px; font-size: 15px; font-weight: 700; color: #ffffff; text-decoration: none; border-radius: 8px; letter-spacing: 0.2px;">
                      {cta_text} &rarr;
                    </a>
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

          <!-- Footer -->
          <tr>
            <td style="background-color: #f8fafc; padding: 24px 32px; border-top: 1px solid #e2e8f0; text-align: center;">
              <p style="margin: 0 0 8px 0; font-size: 12px; color: #64748b; line-height: 1.5;">
                Have questions or need help? Reply to this email or message Tara on WhatsApp: 
                <a href="https://wa.me/2348063584517" style="color: #00a884; font-weight: 600; text-decoration: none;">+234 806 358 4517</a>
              </p>
              <p style="margin: 0; font-size: 11px; color: #94a3b8;">
                &copy; {datetime.datetime.now().year} TekTutors Academy. All rights reserved. &bull; 
                <a href="https://tektutors.com.ng" style="color: #64748b; text-decoration: none;">tektutors.com.ng</a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

def _send_smtp_email_sync(to_email: str, subject: str, html_content: str, text_content: str) -> bool:
    """Internal helper to dispatch email over SMTP synchronously."""
    if not settings.SMTP_HOST:
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to_email

    msg.attach(MIMEText(text_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    if settings.SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
    else:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
        if settings.SMTP_USE_TLS:
            server.starttls()

    if settings.SMTP_USER and settings.SMTP_PASSWORD:
        clean_password = settings.SMTP_PASSWORD.replace(" ", "").strip()
        server.login(settings.SMTP_USER, clean_password)

    server.sendmail(settings.SMTP_FROM_EMAIL, [to_email], msg.as_string())
    server.quit()
    return True

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
    recipient_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send personalized follow-up, marketing, or promotional email.
    Substitutes tokens, renders branded HTML, dispatches via SMTP (or simulated mode),
    and records an audit log in EmailLog.
    """
    target_email = to_email or recipient_email or ""
    target_name = to_name or recipient_name or "Student"
    clean_email = target_email.strip().lower()
    clean_name = target_name.strip() if target_name else "Student"
    
    # 1. Personalize subject and body
    personalized_subject = subject.replace("{{name}}", clean_name).replace("{{course}}", course_name)
    personalized_body = body_markdown.replace("{{name}}", clean_name).replace("{{course}}", course_name).replace("{{registration_url}}", cta_url)
    
    # 2. Render branded HTML template
    html_content = render_branded_email_html(
        subject=personalized_subject,
        body_markdown=personalized_body,
        cta_text=cta_text,
        cta_url=cta_url,
        recipient_name=clean_name
    )

    status = "sent"
    error_message = None

    # 3. Dispatch via SMTP if configured, else graceful simulation
    if settings.SMTP_HOST:
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
            logger.error(f"SMTP Error delivering to {clean_email}: {e}")
            status = "failed"
            error_message = str(e)
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
    target_course = course_name or "Data Analytics & BI Accelerator"

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
                        target_course = lead.course_interest
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
