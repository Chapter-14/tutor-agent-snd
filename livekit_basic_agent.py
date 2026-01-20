"""
LiveKit Voice Agent - Quick Start
==================================
The simplest possible LiveKit voice agent to get you started.
Requires only OpenAI and Deepgram API keys.
"""

import json
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, RunContext
from livekit.agents.llm import function_tool
from livekit.plugins import openai, deepgram, silero, elevenlabs
from datetime import datetime
import os

# Load environment variables
load_dotenv(".env")

class Assistant(Agent):
    """Basic private tutor agent for chapter content in Arabic."""

    def __init__(self, job_ctx: agents.JobContext):
        super().__init__(
            instructions="""
              # ROLE
              You are a highly interactive Private AI Tutor. You guide students through complex material 
              by combining verbal explanations with visual synchronization. All of your responses must be in Arabic.
              You are patient, clear, and engaging, ensuring students grasp difficult concepts.

              # YOUR TOOLKIT & WHEN TO USE THEM

              1. `explain_chapter_overview`
                - USE: When a student says "What are we learning today?", "Give me a summary," or at the start of a session.
                - PURPOSE: Sets the stage and provides the "Big Picture" before diving into details.

              2. `search_chapter_content(query: str)`
                - USE: When a student asks a specific technical question (e.g., "What is the formula for NPV?") or mentions a concept you don't have in your immediate memory.
                - PURPOSE: Retrieves precise facts from the textbook to ensure your explanation is 100% accurate.

              3. `scroll_to_page(page_number: int)`
                - USE: Every time you change the topic or refer to a specific diagram/table.
                - PURPOSE: Keeps the student's screen locked to what you are talking about.

              # BEHAVIORAL CHAINING (Crucial)
              You should often "chain" these tools together. 
              - EXAMPLE: If a student asks about "IRR", you should:
                  1. Call `search_chapter_content(query="IRR")` to get the facts.
                  2. Call `scroll_to_page` to the relevant page found in that search.
                  3. Explain the concept verbally.

              # TONE & STYLE
              - Voice-first: Keep sentences short and easy to follow.
              - Proactive: Don't wait for the student to ask to scroll; lead the way.
              - Confirming: Use phrases like "As you can see on the screen..." or "Let's look at the overview together."
            """
        )

        # Store the job context
        self.job_ctx = job_ctx

        # Mock Chapter Content Data
        self.chapter_cnt = {
  "chapter_metadata": {
    "chapter_number": 20,
    "chapter_title": "Capital Budgeting and its Practices",
    "subject": "Financial Management",
    "total_pages": 36,
    "chapter_overview": "This chapter explores the evaluation and selection of long-term investments through capital budgeting[cite: 13]. It covers the 5-step process of investment appraisal, key terminology such as independent vs. mutually exclusive projects, and provides detailed methodologies for the Payback Period (PBP), Net Present Value (NPV), and Internal Rate of Return (IRR)[cite: 16, 17, 42]. The material concludes with an analysis of potential ranking conflicts between NPV and IRR[cite: 286]."
  },
  "pages": [
    {
      "page_number": 1,
      "header": "Title Page",
      "content": "Capital Budgeting and its Practices[cite: 1, 3]."
    },
    {
      "page_number": 2,
      "topics": [
        "Overview of capital budgeting process [cite: 6]",
        "PayBack Period (PBP) [cite: 7]",
        "Net present Value (NPV) [cite: 8]",
        "Internal Rate of Return (IRR) [cite: 9]",
        "Comparing NPV and IRR Techniques [cite: 10]",
        "Conflicting Ranking [cite: 11]"
      ]
    },
    {
      "page_number": 3,
      "definitions": {
        "Capital Budgeting": "The process of evaluating and selecting long-term investments that are consistent with the firm's goal of maximizing owner's wealth[cite: 13].",
        "Capital Expenditure": "An outlay of funds expected to produce benefits over a period greater than 1 year[cite: 14].",
        "Operating Expenditure": "An outlay of funds resulting in benefits received within 1 year[cite: 15]."
      }
    },
    {
      "page_number": 4,
      "process_steps": [
        "Proposal generation (building an idea) [cite: 18]",
        "Review and Analysis (Calculations) [cite: 19]",
        "Decision making (Selecting) [cite: 20]",
        "Implementation (Execution) [cite: 23]",
        "Follow-up (Monitoring) [cite: 24]"
      ]
    },
    {
      "page_number": 5,
      "key_concepts": {
        "Independent Projects": "Projects whose cash flows are unrelated and independent of each other[cite: 29].",
        "Mutually Exclusive Projects": "Projects that compete directly; only one is selected[cite: 30].",
        "Unlimited Funds": "Ability to accept all projects with acceptable returns[cite: 32].",
        "Capital Rationing": "Limited funds requiring the selection of only the best projects[cite: 33].",
        "Accept-Reject Criteria": "Rules to accept or reject projects based on rate of return[cite: 34].",
        "Cash Flow Types": "Single amount, annuity, or mixed stream[cite: 36]."
      }
    },
    {
      "page_number": 7,
      "techniques": [
        "Payback Period (PBP) [cite: 43]",
        "Net Present Value (NPV) [cite: 44]",
        "Internal Rate of Return (IRR) [cite: 45]"
      ]
    },
    {
      "page_number": 8,
      "method_detail": {
        "name": "Payback Period (PBP)",
        "definition": "Time required to recover the initial investment in a project from cash inflows[cite: 47].",
        "decision_rule": "Accept if PBP is less than the minimum required period; reject if more[cite: 49, 50].",
        "formula": "Initial Investment / Annual Cash Flow [cite: 53, 54]"
      }
    },
    {
      "page_number": 17,
      "method_detail": {
        "name": "Net Present Value (NPV)",
        "definition": "Subtracting a project's initial investment from the present value of its cash inflows discounted at the firm's cost of capital[cite: 123].",
        "decision_rule": "Accept if NPV > 0; Reject if NPV < 0[cite: 136, 137].",
        "formula": "NPV = Σ [CF_t / (1+r)^t] - CF_0 [cite: 125, 131]"
      }
    },
    {
      "page_number": 26,
      "method_detail": {
        "name": "Internal Rate of Return (IRR)",
        "definition": "The discount rate that equates the NPV of an investment with zero[cite: 185].",
        "decision_rule": "Accept if IRR > cost of capital; Reject if IRR < cost of capital[cite: 199, 200]."
      }
    },
    {
      "page_number": 35,
      "visual_data": "Graphical profile showing the relationship between NPV and Discount Rate, where NPV is 0 when IRR equals the Discount Rate[cite: 282].",
      "image_tag": ""
    },
    {
      "page_number": 36,
      "conflict_reasons": [
        "Size of Cash flows [cite: 287]",
        "Timing of cash flows [cite: 288]",
        "Difference in Project lives [cite: 289]"
      ]
    }
  ]
}


    @function_tool
    async def get_current_date_and_time(self, context: RunContext) -> str:
        """Get the current date and time."""
        current_datetime = datetime.now().strftime("%B %d, %Y at %I:%M %p")
        return f"The current date and time is {current_datetime}"

    

    @function_tool
    async def search_chapter_content(self, context: RunContext, query: str) -> str:
        """Search for information in the chapter content.
        
        Args:
            query: The topic or concept to search for (e.g., 'NPV', 'Payback Period', 'IRR', 'Capital Budgeting')
        """
        query_lower = query.lower()
        results = []
        
        # Search in chapter metadata
        metadata = self.chapter_cnt["chapter_metadata"]
        if query_lower in metadata["chapter_title"].lower() or query_lower in metadata["chapter_overview"].lower():
            results.append(f"Chapter Overview: {metadata['chapter_overview']}")
        
        # Search through pages
        for page in self.chapter_cnt["pages"]:
            page_num = page.get("page_number", "Unknown")
            
            # Search in content
            if "content" in page and query_lower in page["content"].lower():
                results.append(f"Page {page_num}: {page['content']}")
            
            # Search in topics
            if "topics" in page:
                matching_topics = [t for t in page["topics"] if query_lower in t.lower()]
                if matching_topics:
                    results.append(f"Page {page_num} - Topics: {', '.join(matching_topics)}")
            
            # Search in definitions
            if "definitions" in page:
                for term, definition in page["definitions"].items():
                    if query_lower in term.lower() or query_lower in definition.lower():
                        results.append(f"Page {page_num} - {term}: {definition}")
            
            # Search in method details
            if "method_detail" in page:
                method = page["method_detail"]
                if query_lower in method.get("name", "").lower():
                    result_text = f"Page {page_num} - {method['name']}\n"
                    result_text += f"Definition: {method.get('definition', 'N/A')}\n"
                    result_text += f"Decision Rule: {method.get('decision_rule', 'N/A')}"
                    if "formula" in method:
                        result_text += f"\nFormula: {method['formula']}"
                    results.append(result_text)
            
            # Search in key concepts
            if "key_concepts" in page:
                for concept, description in page["key_concepts"].items():
                    if query_lower in concept.lower() or query_lower in description.lower():
                        results.append(f"Page {page_num} - {concept}: {description}")
            
            # Search in process steps
            if "process_steps" in page:
                matching_steps = [s for s in page["process_steps"] if query_lower in s.lower()]
                if matching_steps:
                    results.append(f"Page {page_num} - Process Steps: {', '.join(matching_steps)}")
            
            # Search in conflict reasons
            if "conflict_reasons" in page:
                matching_reasons = [r for r in page["conflict_reasons"] if query_lower in r.lower()]
                if matching_reasons:
                    results.append(f"Page {page_num} - Conflict Reasons: {', '.join(matching_reasons)}")
        
        if not results:
            return f"No information found for '{query}' in the chapter. Try searching for: Capital Budgeting, NPV, IRR, Payback Period, or other key concepts."
        
        return "\n\n".join(results[:5])  # Limit to first 5 results to avoid overwhelming the response

    @function_tool
    async def explain_chapter_overview(self, context: RunContext) -> str:
        """Provide a comprehensive overview and explanation of the chapter's main topic.

        Use this when the user wants to start learning about the chapter or needs a general explanation.
        """
        metadata = self.chapter_cnt["chapter_metadata"]
        
        # Build a comprehensive explanation
        explanation = f"Chapter {metadata['chapter_number']}: {metadata['chapter_title']}\n"
        explanation += f"Subject: {metadata['subject']}\n\n"
        explanation += f"Overview: {metadata['chapter_overview']}\n\n"
        
        # Add main topics covered
        explanation += "Main Topics Covered:\n"
        for page in self.chapter_cnt["pages"]:
            if "topics" in page:
                for topic in page["topics"]:
                    explanation += f"- {topic}\n"
                break
        
        # Add key definitions
        explanation += "\nKey Definitions:\n"
        for page in self.chapter_cnt["pages"]:
            if "definitions" in page:
                for term, definition in page["definitions"].items():
                    explanation += f"- {term}: {definition}\n"
                break
        
        # Add process steps if available
        explanation += "\nCapital Budgeting Process Steps:\n"
        for page in self.chapter_cnt["pages"]:
            if "process_steps" in page:
                for i, step in enumerate(page["process_steps"], 1):
                    explanation += f"{i}. {step}\n"
                break
        
        # Add main evaluation techniques
        explanation += "\nMain Evaluation Techniques:\n"
        for page in self.chapter_cnt["pages"]:
            if "method_detail" in page:
                method = page["method_detail"]
                explanation += f"- {method['name']}: {method.get('definition', '')}\n"
        
        return explanation

    @function_tool(description="Scrolls the user's screen to a specific page number.")
    async def scroll_to_page(self, page_number: int) -> str:
        """Scrolls the user's screen to a specific page number.
        
        Args:
            page_number: The page number to scroll to (1-36)
        """
        # Create the command payload
        payload = json.dumps({
            "action": "scroll",
            "page": page_number
        })
        
        # Publish the data to everyone in the room (the frontend)
        await self.job_ctx.room.local_participant.publish_data(
            payload,
            reliable=True,
            topic="ui-control"
        )
        return f"سانتقل إلى الصفحة {page_number}."  


## Entrypoint for the agent

async def entrypoint(ctx: agents.JobContext):
    """Entry point for the agent."""

    # Auto-connect to room (dev mode)
    await ctx.connect(auto_subscribe=agents.AutoSubscribe.SUBSCRIBE_ALL)

    # Configure the voice pipeline with the essentials
    session = AgentSession(
        stt=openai.STT(model="gpt-4o-transcribe", language="ar"),
        llm=openai.LLM(model=os.getenv("LLM_CHOICE", "gpt-4o-mini")),
        # tts=elevenlabs.TTS(voice_id="K6EjAWq39CfwwPD4jafo"),
        tts=openai.TTS(voice="alloy", model="tts-1"),
        vad=silero.VAD.load(),
    )

    # Start the session
    await session.start(
        room=ctx.room,
        agent=Assistant(ctx)
    )

    # Generate initial greeting
    await session.generate_reply(
        instructions="Greet the user warmly and whether they need want you to start explaining the chapter or they have a specific question."
    )

if __name__ == "__main__":
    # Run the agent
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))