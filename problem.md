The Cold Start challenge
We're building Xpert, a personal assistant that lives in WhatsApp. Before an assistant can help anyone, it has to understand their life. This challenge is that first step, and it's how we choose our winter interns.

Now
Starter kit. The data follows by 3 Nov, sooner if ready
12 Nov, 23:59 IST
Submit your repo
From 16 Nov
Calls with shortlisted candidates, then offers
Why this problem
A personal assistant is only useful if it understands the person it works for. "Call Ravi about the payment" means one thing if Ravi is your accountant and something else if he's your brother-in-law. A message about the cook's leave matters to whoever runs the house, and is noise to everyone else.

So understanding a person's life comes first. Only once you know who the people around them are, and what they care about, can you tell which tasks are really theirs and how to help with each one.

Today Xpert understands one person's life well: our founder's. That's because he sat down and told it who everyone is. "This is my wife. This is the cook at home. These five people run this company with me. This is what I want from this year." A new user won't do that. They'll connect WhatsApp and expect the assistant to understand them from day one. That's the cold start problem.

Your task, in one line
You get a few weeks of one person's WhatsApp. Read it the way a sharp new assistant would on their first day, and work out three things:

1. Their people
Who everyone is and how each person relates to them, and the companies, home and groups they're part of.
2. What they care about
The goals that show up in what they talk about.
3. What's open
The tasks still in motion, which ones got done, and where an assistant should step in or stay out.
Your program writes all of this to one file, and we score it against the answers the real person gave us. The details follow.

The words we use
These are the same words our own system uses. Your output uses them too.

Circle
A person's one relationship to the user. Everyone is in exactly one circle, in every chat. A circle isn't about closeness: the cook at home and the office cleaner are both staff.

spouse
child
parent
in-law
sibling
relative
friend
colleague
client
vendor
partner
staff
Organisation
Something the user runs or belongs to, with its own people and chats: a company, the home, a holiday home, the housing society, the kids' school. Each has a type, a side (home or work) and the user's role in it (owner, partner, helper, resident, parent). A client's company is not an organisation: a client is a person in the client circle.

Link
How a person relates to an organisation. runs: they run it with the user, like a colleague or partner. supports: they work for it, like a cook, driver or office cleaner.

Goal
Something the user is working towards. It belongs to one area, has a horizon (3mo, 1yr, 3yr, 5yr) and a type: a habit is a rhythm, like running three times a week; a milestone is a target, like ten paying clients by March; an experience is something to plan and do, like a trip.

self
spouse
kids
parents
work
friends
experiences
finances
health
home
Open loop
Something still in motion. A commitment: the user promised something. A followup: the user is waiting on someone else. A deadline: something is due on a date. A question: the user must decide or answer something. At any moment a loop is open, done or dropped.

Assist
When the assistant moves a loop forward itself, for example by finding options, drafting a reply or booking a slot, instead of only reminding the user. Assist does everything private and reversible on its own. It asks the user only before something leaves his phone or can't be undone.

What you get
A WhatsApp history of one person, Arjun, covering about eight weeks: more than 300 chats and about 20,000 messages, from family and staff to his companies, clients, vendors and friends' groups.

Arjun is real, but his chats are not. We went through every message from a real person's life and changed every name, number, company and specific place, and moved every amount. Only big cities, public brands and dates stay as they were. What stays real is the shape: who talks to whom, how often, the mix of English, Hindi, Bengali and Hinglish, the voice notes, the half-finished threads, the "ok" that means done and the "ok" that doesn't. Please don't try to work out who it is based on. Delete the data when the challenge ends.

Dev set: the first two weeks, with our answers, so you can measure yourself.
Hidden set: the six weeks after. You never see it. We run your code on it. Every name in it was changed a second time, differently, so nothing you learn about a person from the dev answers carries over. Your system has to work it out again, the way it would for a new user.
Open loops are scored on the last two weeks of the hidden set. The weeks before are there for context, as they would be in real life.
chats.jsonl      one line per chat: chat_id, name, is_group, participant ids
messages.jsonl   one line per message: id, chat_id, sender_id, sender_name (as saved
                 in Arjun's phone), ts, kind (text | voice_transcript |
                 image_caption | document), body, quoted_id
seed.json        what Arjun told us when he signed up: the circle for about 20%
                 of his people, the names of two of his organisations, one goal
answers/         dev set only: the answer key for those two weeks
Arjun's own id is ME. Everyone else has a stable id that is the same in every week.

What your program must produce
One command reads a folder like the one above and writes output.json. The schema is in schema.json in the starter kit. It has five parts.

People
For each person, their circle and their links to organisations. Some staff also look after a specific person, like a driver who looks after the kids. Note that too.

Organisations and chats
Arjun's organisations, each with its type, side and his role. Then tie every chat to one person or one organisation. A group can belong to a person: a child's class parents' group belongs to the child. Name organisations however you like. We match them by the chats and people you attach to them, not by name.

Goals
Up to 10 goals you think Arjun holds, each with its area, type, horizon, and the messages that show it. Many goals never come up in a few weeks of chat, so we only score goals that actually appear in the data. A goal you invent without evidence costs points.

Open loops
Every loop in the data. For each one give a title and its type; who owes it (Arjun, or another person's id); the chat and the message it came from; a due date if there is one; its status at the end of the data (open, done or dropped); and for done or dropped, the message that shows it.

Where to help
For each loop that is still open, choose one:

assist: the assistant can move it forward itself. Give the next step in one line, and say whether that step needs Arjun's yes.
remind: only Arjun can do it, so remind him once at the right time. Give the time.
leave: stay out of it. It's someone else's to handle, it's too personal, or a reminder would only annoy him. Say which.
Knowing when to stay quiet matters as much as knowing when to help. An assistant that pokes Arjun about his wife's messages, or offers to "help" with something his staff already handle, gets switched off.

You don't have to do everything. Each part is scored on its own. A strong solution to three parts beats a weak one to all five. Tell us in your write-up what you chose to focus on and why.

How we score it
We run your code once on the hidden set, in a clean container with no internet except the model endpoint, and a 30-minute limit.

Part	How	Points
Circles	Correct circle per person, people from seed.json excluded	12
Organisations	How well yours match ours, by their chats and people	8
Chats	Each chat tied to the right person or organisation	8
Goals	Goals that match ours, each with real evidence. Invented ones cost points	8
Open loops found	Precision and recall against our list	14
Open loops closed right	Status matches ours. Saying "done" when it isn't costs more than missing a done	14
Where to help	Your call matches Arjun's own. A wrong assist or remind on a leave costs most	10
Cost	Dollars per 1,000 messages, measured by us	12
Your write-up	Mostly: how well your predicted failures match your real ones	7
Runs with one command	Clean install, one command, finishes in 30 minutes	7
Total		100
The starter kit has a checker that tells you whether your output is in the right shape and how it scores on the dev set. With the data we also publish our own baseline's score and cost. Beat it, or tell us honestly why not.

Models and cost
Use any model that has an OpenAI-compatible API. Most providers offer one. Your code reads LLM_BASE_URL, LLM_API_KEY and LLM_MODEL from the environment, so we can run it with our own key.
You pay for your own testing. We don't hand out keys. Several providers have free tiers or free models that are enough to build and test this. Finding a cheap way to work is part of the challenge.
When we score, we run your code with our own key, on the model you name, and count every token.
No fine-tuned or self-hosted models. Ordinary code like rules, regexes, embeddings or small local libraries is welcome. A solution that uses no model where none is needed is a good one.
What you send us
A GitHub repo. A private repo is fine if you add rmaslunia as a collaborator. It should contain:

Your code, with a run.sh that takes an input folder and an output path.
WRITEUP.md, at most 2 pages: what you focused on and why; your approach; what it costs and where the money goes; and where it's wrong: the kinds of mistakes you expect, and roughly how often.
ai-logs/: the transcripts of your sessions with Claude, Codex, Cursor or ChatGPT. Using AI is expected. We read these to see how you work, not to count how much you used it.
Don't commit the data. The starter kit's .gitignore already leaves it out.

Rules
Solo work. You can talk about ideas with others, but don't share code or results.
Your code can send the data only to the model endpoint.
The solution stays yours. We use it only to evaluate you.
After you submit
We'll shortlist the strongest submissions and hold a 45-minute call with each from 16 November. On the call we go through your code base and your approach: you'll spend 10 minutes walking us through it. Then Arjun corrects something your system got wrong, the way a real user would say it, and you change your system live with your own AI tools. We want to see whether you can take a correction without breaking what already worked. The last part is a conversation about our real numbers. Final offers go out after the calls.