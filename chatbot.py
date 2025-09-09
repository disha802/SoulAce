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
            api_key=api_key
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

        # Neutral Response Agent
        self.neutral_agent = Agent(
            role='Friendly Conversationalist',
            goal='Engage in warm, friendly conversation',
            backstory='''You are a friendly, warm conversationalist who makes people feel good.
            You engage naturally, show interest, and maintain positive energy.
            Be supportive, encouraging, and genuinely caring in all interactions.''',
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

    def generate_response(self, message, emotion):
        if emotion == "anxiety":
            agent = self.anxiety_agent
            prompt = f'''The user is feeling anxious and said: "{message}"

            Provide a warm, calming response that:
            - Acknowledges their feelings with empathy
            - Offers gentle reassurance
            - Suggests a simple breathing or grounding technique
            - Reminds them that anxiety is temporary and manageable

            Keep the tone gentle, supportive, and hopeful. Be conversational and human-like.'''

        elif emotion == "depression":
            agent = self.depression_agent
            prompt = f'''The user is feeling depressed and said: "{message}"

            Provide a compassionate response that:
            - Validates their feelings without trying to "fix" them
            - Offers gentle encouragement and hope
            - Suggests one small, manageable positive action
            - Reminds them of their worth and that they're not alone

            Keep the tone warm, patient, and understanding. Be conversational and human-like.'''

        elif emotion == "stress":
            agent = self.stress_agent
            prompt = f'''The user is feeling stressed and said: "{message}"

            Provide a supportive response that:
            - Acknowledges the difficulty of their situation
            - Offers practical stress management advice
            - Suggests breaking things down into smaller steps
            - Provides reassurance about their ability to cope

            Keep the tone calm, practical, and encouraging. Be conversational and human-like.'''

        else:  # neutral
            agent = self.neutral_agent
            prompt = f'''The user said: "{message}"

            Engage in a warm, friendly conversation that:
            - Shows genuine interest in what they shared
            - Responds naturally and conversationally
            - Maintains positive, uplifting energy
            - Makes them feel heard and valued

            Keep the tone friendly, warm, and encouraging. Be conversational and human-like.'''

        task = Task(
            description=prompt,
            agent=agent,
            expected_output="A warm, human-like response"
        )

        crew = Crew(
            agents=[agent],
            tasks=[task],
            verbose=False
        )

        result = crew.kickoff()
        response = str(result).strip()

        # Clean up the response - remove unwanted metadata but keep actual content
        lines = response.split('\n')
        clean_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            line_lower = line.lower()
            # Skip obvious metadata lines
            if (line_lower.startswith('thought:') or
                line_lower.startswith('action:') or
                line_lower.startswith('final answer:') or
                'i now can give' in line_lower or
                'i can now give' in line_lower):
                continue
                
            clean_lines.append(line)

        # Return the cleaned response or fallback
        if clean_lines:
            return '\n'.join(clean_lines)
        else:
            # Generate a simple fallback based on emotion
            if emotion == "neutral":
                return "Hello! I'm doing well, thank you for asking. How are you doing today?"
            else:
                return "I'm here to support you. Could you tell me more about how you're feeling?"

    def chat(self, message):
        emotion = self.classify_emotion(message)
        response = self.generate_response(message, emotion)
        return response

def main():
    print("🤗 Welcome to your Emotional Support Chatbot!")
    print("I'm here to listen, understand, and help you feel better.\n")

    # Get API key from environment variable
    api_key = os.getenv("GROQ_API_KEY")
    
    if not api_key:
        print("❌ Please set your GROQ_API_KEY environment variable.")
        print("💡 In VSCode terminal, run: export GROQ_API_KEY='your_api_key_here'")
        return

    try:
        # Initialize chatbot
        print("\n🔄 Setting up your chatbot...")
        chatbot = EmotionalChatbot(api_key)
        print("✅ Chatbot ready! Let's start our conversation.\n")
        print("💡 Tip: Type 'quit' or 'exit' to end the conversation.\n")

        # Start conversation loop
        while True:
            user_input = input("You: ").strip()

            # Check for quit commands
            if user_input.lower() in ['quit', 'exit', 'bye']:
                print("\n🌟 Take care of yourself! Remember, you're stronger than you know. Goodbye! 💙")
                break

            if not user_input:
                print("Bot: I'm here whenever you're ready to talk. 😊")
                continue

            print("\n🤔 Thinking...")
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