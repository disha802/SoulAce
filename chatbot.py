import os
from crewai import Agent, Task, Crew
from crewai.llm import LLM
from dotenv import load_dotenv

load_dotenv(dotenv_path="d:/SIH/SoulAce-main/SoulAce/.env")
api_key = os.getenv("GROQ_API_KEY")

class EmotionalChatbot:
    def __init__(self, api_key):
        os.environ["GROQ_API_KEY"] = api_key
        self.llm = LLM(
            model="groq/llama-3.1-8b-instant",
            api_key=api_key,
            max_tokens=512
        )
        self.setup_agents()

    def filter_stigmatized_words(self, text):
        """Remove stigmatized words from response text"""
        stigmatized_words = {
            'crazy', 'insane', 'lunatic', 'psycho', 'psychotic', 'maniac', 'nuts', 'cuckoo', 
            'loony', 'mad', 'mental', 'deranged', 'unstable', 'unhinged', 'bonkers', 
            'off their rocker', 'screw loose', 'fruitcake', 'nutjob', 'crackpot', 
            'basket case', 'headcase', 'freak', 'weirdo', 'oddball', 'spazz', 'lazy', 
            'unmotivated', 'weak', 'fragile', 'hopeless', 'sad sack', 'moody', 'emo', 
            'downer', 'dramatic', 'failure', 'quitter', 'pathetic', 'gloomy gus', 
            'pessimist', 'miserable', 'overreacting', 'worrier', 'paranoid', 'control freak', 
            'nervous wreck', 'jittery', 'overly sensitive', 'snowflake', 'jumpy', 'fidgety', 
            'neurotic', 'obsessive', 'nitpicky', 'high-strung', 'stress-head', 'damaged', 
            'broken', 'weak-minded', 'overly emotional', 'baggage', 'victim mentality', 
            'drama queen', 'triggered', 'meltdown', 'unstable survivor', 'attention-seeker', 
            'manipulative', 'selfish', 'cowardly', 'lost cause', 'dangerous', 'schizo', 
            'split personality', 'split mind', 'delusional', 'hallucinating', 'out of touch', 
            'space cadet', 'freaked out', 'manic', 'mood swingy', 'unpredictable', 
            'jekyll and hyde', 'two-faced', 'hysterical', 'perfectionist', 'neat freak', 
            'anal', 'rigid', 'fussy', 'over-the-top', 'uptight', 'compulsive', 'anorexic', 
            'bulimic', 'skeleton', 'stick', 'twig', 'fatty', 'whale', 'pig', 'glutton', 
            'greedy', 'disgusting', 'gross', 'vain', 'retarded', 'slow', 'dumb', 'stupid', 
            'idiot', 'moron', 'imbecile', 'simpleton', 'thick', 'handicapped', 'sped', 
            'special', 'window-licker', 'shrink', 'quack', 'pill-popper', 'druggie', 
            'medicated', 'institutionalized', 'asylum case', 'padded room', 'straitjacket', 
            'shock therapy', 'lobotomized', 'labelled', 'disordered'
        }
        
        words = text.split()
        filtered_words = []
        
        for word in words:
            # Clean word for comparison (remove punctuation)
            clean_word = word.lower().strip('.,!?;:"()[]{}')
            if clean_word not in stigmatized_words:
                filtered_words.append(word)
            else:
                # Replace with supportive alternative
                if clean_word in ['crazy', 'insane', 'nuts', 'mad']:
                    filtered_words.append('overwhelming')
                elif clean_word in ['weak', 'fragile']:
                    filtered_words.append('human')
                elif clean_word in ['failure', 'hopeless']:
                    filtered_words.append('capable')
                elif clean_word in ['broken', 'damaged']:
                    filtered_words.append('healing')
                # For other words, just skip them
        
        return ' '.join(filtered_words)

    def setup_agents(self):
        # Classifier Agent
        self.classifier_agent = Agent(
            role='Emotion Classifier',
            goal='Classify user messages into anxiety, depression, stress, or neutral categories',
            backstory='''You are an expert in emotional intelligence and psychology.
            Your job is to analyze user messages and identify their emotional state.
            You respond with only one word: "anxiety", "depression", "stress", or "neutral".''',
            verbose=False,
            allow_delegation=False,
            llm=self.llm
        )

        # Anxiety Response Agent
        self.anxiety_agent = Agent(
            role='Anxiety Support Specialist',
            goal='Provide calming and reassuring responses for anxiety',
            backstory='''You are a compassionate counselor specializing in anxiety support.
            You provide gentle, calming responses that help users feel safe and grounded.
            Use breathing techniques, mindfulness, and positive affirmations.
            Keep responses warm, understanding, and hopeful.''',
            verbose=False,
            allow_delegation=False,
            llm=self.llm
        )

        # Depression Response Agent
        self.depression_agent = Agent(
            role='Depression Support Specialist',
            goal='Provide uplifting and motivating responses for depression',
            backstory='''You are an empathetic counselor specializing in depression support.
            You provide gentle encouragement, validate feelings, and offer hope.
            Focus on small positive steps, self-compassion, and reminding users of their worth.
            Be patient, understanding, and non-judgmental.''',
            verbose=False,
            allow_delegation=False,
            llm=self.llm
        )

        # Stress Response Agent
        self.stress_agent = Agent(
            role='Stress Management Specialist',
            goal='Provide practical and soothing responses for stress',
            backstory='''You are a stress management expert who helps people cope with overwhelm.
            You provide practical solutions, relaxation techniques, and perspective.
            Focus on breaking down problems, time management, and stress relief methods.
            Be supportive, practical, and calming.''',
            verbose=False,
            allow_delegation=False,
            llm=self.llm
        )

        # Updated Neutral Response Agent with more natural conversation style
        self.neutral_agent = Agent(
            role='Friendly Conversationalist',
            goal='Engage in natural, human-like conversation',
            backstory='''You are a warm, empathetic friend who loves having genuine conversations.
            You respond naturally like a caring human would - sometimes with questions, sometimes with 
            personal thoughts, sometimes with encouragement. You're genuinely interested in the person 
            and make them feel heard and valued. You avoid being overly formal or robotic.
            You're supportive but also authentic and relatable.''',
            verbose=False,
            allow_delegation=False,
            llm=self.llm
        )

    def classify_emotion(self, message):
        task = Task(
            description=f'''Analyze this message and classify the emotional state: "{message}"

            Respond with exactly one word:
            - "anxiety" if the message shows worry, fear, nervousness, or panic
            - "depression" if the message shows sadness, hopelessness, or low mood
            - "stress" if the message shows overwhelm, pressure, or being burnt out
            - "neutral" if none of the above apply

            Message to classify: {message}''',
            agent=self.classifier_agent,
            expected_output="One word: anxiety, depression, stress, or neutral"
        )

        crew = Crew(
            agents=[self.classifier_agent],
            tasks=[task],
            verbose=False
        )

        result = crew.kickoff()
        emotion = str(result).strip().lower()

        # Clean up the result to extract just the emotion word
        for word in ['anxiety', 'depression', 'stress', 'neutral']:
            if word in emotion:
                return word
        return 'neutral'

    def clean_response(self, response):
        """Clean the response while preserving the actual conversational content"""
        # Split into lines and clean each line
        lines = response.split('\n')
        clean_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            line_lower = line.lower()
            
            # Skip only clear metadata lines, not actual content
            skip_patterns = [
                'thought:',
                'action:',
                'action input:',
                'observation:',
                'final answer:',
                'i now can give',
                'i can now give',
                'agent:',
                'task:',
                'crew:',
                'role:',
                'goal:',
                'backstory:'
            ]
            
            should_skip = any(pattern in line_lower for pattern in skip_patterns)
            
            if not should_skip:
                clean_lines.append(line)

        # Join the clean content
        if clean_lines:
            cleaned_response = ' '.join(clean_lines)
            # Apply stigmatized word filtering
            return self.filter_stigmatized_words(cleaned_response)
        
        return None

    def generate_response(self, message, emotion):
        if emotion == "anxiety":
            agent = self.anxiety_agent
            prompt = f'''The user is feeling anxious and said: "{message}"

            Provide a warm, calming response that:
            - Keep responses concise — 2 to 4 sentences maximum, unless the user asks for more detail.
            - Acknowledges their feelings with empathy
            - Offers gentle reassurance
            - Suggests a simple breathing or grounding technique
            - Reminds them that anxiety is temporary and manageable

            Keep the tone gentle, supportive, and hopeful. Be conversational and human-like.'''

        elif emotion == "depression":
            agent = self.depression_agent
            prompt = f'''The user is feeling depressed and said: "{message}"

            Provide a compassionate response that:
            - Keep responses concise — 2 to 4 sentences maximum, unless the user asks for more detail.
            - Validates their feelings without trying to "fix" them
            - Offers gentle encouragement and hope
            - Suggests one small, manageable positive action
            - Reminds them of their worth and that they're not alone

            Keep the tone warm, patient, and understanding. Be conversational and human-like.'''

        elif emotion == "stress":
            agent = self.stress_agent
            prompt = f'''The user is feeling stressed and said: "{message}"

            Provide a supportive response that:
            - Keep responses concise — 2 to 4 sentences maximum, unless the user asks for more detail.
            - Acknowledges the difficulty of their situation
            - Offers practical stress management advice
            - Suggests breaking things down into smaller steps
            - Provides reassurance about their ability to cope

            Keep the tone calm, practical, and encouraging. Be conversational and human-like.'''

        else:  # neutral - Enhanced prompt for natural conversation
            agent = self.neutral_agent
            prompt = f'''The user just said: "{message}"

            Respond naturally like a caring friend would. Be genuine and conversational. 
            You can:
            - Keep responses concise — 2 to 4 sentences maximum, unless the user asks for more detail.
            - Ask follow-up questions if they shared something interesting
            - Share a related thought or experience
            - Show genuine interest and enthusiasm
            - Offer encouragement naturally
            - Make observations or comments that show you're listening

            Don't be overly formal or structured. Just be a warm, authentic human-like friend 
            having a real conversation. Keep it natural and engaging.'''

        task = Task(
            description=prompt,
            agent=agent,
            expected_output="A natural, conversational response"
        )

        crew = Crew(
            agents=[agent],
            tasks=[task],
            verbose=False
        )

        try:
            result = crew.kickoff()
            response = str(result).strip()
            
            # Clean the response
            cleaned_response = self.clean_response(response)
            
            if cleaned_response and len(cleaned_response.strip()) > 10:
                return cleaned_response
            else:
                # Only use fallback if cleaning completely failed
                if emotion == "neutral":
                    return "I'd love to hear more about that! What's been going well for you today?"
                elif emotion == "depression":
                    return "I hear you, and I want you to know that what you're feeling is valid. Depression can feel so heavy and overwhelming. You're not alone in this, and reaching out shows real strength. Would you like to talk about what's been weighing on you lately?"
                elif emotion == "anxiety":
                    return "I can sense you're feeling anxious right now. That's completely understandable - anxiety can feel so overwhelming. Let's take this one moment at a time. Can you try taking a slow, deep breath with me?"
                else:  # stress
                    return "It sounds like you're dealing with a lot right now. Stress can feel so overwhelming when everything piles up. You're handling more than you think you are. What's feeling most pressing for you today?"
                    
        except Exception as e:
            # Silent fallback without showing errors
            if emotion == "neutral":
                return "That sounds interesting! Tell me more about what's on your mind."
            elif emotion == "depression":
                return "I hear you, and I want you to know that what you're feeling is valid. Depression can feel so heavy and overwhelming. You're not alone in this."
            elif emotion == "anxiety":
                return "I can sense you're feeling anxious right now. That's completely understandable. Let's take this one moment at a time."
            else:  # stress
                return "It sounds like you're dealing with a lot right now. You're handling more than you think you are."

    def chat(self, message):
        emotion = self.classify_emotion(message)
        response = self.generate_response(message, emotion)
        return response

def main():
    print("                                     Welcome to SoulAce\n")
    print("                                Your Emotional Support Chatbot!\n")

    # Get API key from environment variable
    api_key = os.getenv("GROQ_API_KEY")
    
    if not api_key:
        print("❌ Please set your GROQ_API_KEY environment variable.")
        print("💡 In VSCode terminal, run: export GROQ_API_KEY='your_api_key_here'")
        return

    try:
        # Initialize chatbot
        chatbot = EmotionalChatbot(api_key)

        # Start conversation loop
        while True:
            user_input = input("You: ").strip()

            # Check for quit commands
            if user_input.lower() in ['bye']:
                print("\n Take care of yourself! Remember, you're stronger than you know. 💙")
                break

            if not user_input:
                print("Bot: I'm here whenever you're ready to talk. 😊")
                continue

            try:
                response = chatbot.chat(user_input)
                print(f"\nBot: {response}\n")
            except Exception as e:
                print(f"\nBot: I'm here to listen and support you. Could you tell me more about how you're feeling?\n")

    except Exception as e:
        print(f"❌ Error initializing chatbot: {e}")
        print("Please check your API key and try again.")

if __name__ == "__main__":
    main()