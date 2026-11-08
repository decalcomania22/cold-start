"""Build a fully synthetic Cold Start dataset with its own answer key (new person, new names, new world).
usage: python tools/make_synth.py [out_dir=data/synth]
Covers every circle, organisation type and role, both link kinds, looks_after, all goal areas/types/horizons,
all loop types and statuses, and assist (with and without his yes) / remind / leave (each reason).
Four weeks; like the hidden set, loops are scored on the last two (answers.loops_scored_from)."""
import json, os, random, sys
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
D0 = datetime(2026, 9, 7, tzinfo=IST)  # Monday; data runs 28 days to Sun 4 Oct 2026
DAYS = 28
SCORED_FROM_DAY = 14
rnd = random.Random(7)

ME_NAME = "Nikhil Arora"
# id: (saved name, circle or None if not in the key)
PEOPLE = {
    "P01": ("Priya ❤️", "spouse"), "P02": ("Aarav", "child"), "P03": ("Myra", "child"),
    "P04": ("Papa", "parent"), "P05": ("Mummy", "parent"),
    "P06": ("Shobha Mummyji", "in-law"), "P08": ("Karan Jiju", "in-law"),
    "P07": ("Neha Didi", "sibling"), "P09": ("Sunil Chacha", "relative"), "P10": ("Rahul Arora", "relative"),
    "P11": ("Lakshmi", "staff"), "P12": ("Raju Driver", "staff"), "P13": ("Kamla Didi", "staff"),
    "P14": ("Bhola Alibaug", "staff"), "P35": ("Sunil Front Desk", "staff"), "P36": ("Joseph Palm Grove", "staff"),
    "P51": ("Salim SLL Driver", "staff"),
    "P15": ("Meghna Saffron", "colleague"), "P16": ("Tarun Ops", "colleague"), "P17": ("Ankit Finance", "colleague"),
    "P18": ("Faiz Warehouse", "colleague"), "P50": ("Pintu Bhiwandi", "colleague"), "P52": ("Rakesh Dispatch", "colleague"),
    "P21": ("Sana K&C", "colleague"), "P22": ("Mehta ji", "colleague"),
    "P19": ("Zoya Khan", "partner"), "P40": ("Deepak Nair FleetX", "partner"),
    "P23": ("Sandeep Freshkart", "client"), "P24": ("Ritu Mehra", "client"), "P25": ("Vikas BuildCo", "client"),
    "P26": ("Gupta CA", "vendor"), "P27": ("Shalini Interiors", "vendor"), "P28": ("PixelPress Printers", "vendor"),
    "P29": ("Ramesh AC", "vendor"), "P30": ("Tapas Da Furniture", "vendor"), "P42": ("Coach Vinod", "vendor"),
    "P43": ("Dr Shah Ortho", "vendor"), "P44": ("Meenal Travels", "vendor"), "P45": ("Juhu Flying Club", "vendor"),
    "P31": ("Dev Kapoor", "friend"), "P32": ("Ishaan", "friend"), "P33": ("Farhan", "friend"),
    "P34": ("Aditi Rao", "friend"), "P53": ("Varun", "friend"), "P54": ("Kunal Sheth", "friend"),
    "P37": ("Mrs Kulkarni B-702", "friend"), "P39": ("Rtn Suresh Iyer", "friend"),
    # in group chats only; their circle is not clear from the data, so they are not in the key
    "P55": ("Sneha (Kabir's mom)", None), "P56": ("Anjali Class Rep", None), "P57": ("Rohit Dsouza", None),
    "P58": ("Pooja M", None), "P59": ("+91 98201 44562", None), "P60": ("Harsh Annual Day", None),
    "P61": ("Arvind B-1103", None), "P62": ("Leena B-404", None), "P63": ("Rtn Mahesh", None),
    "P64": ("Rtn Farida", None), "P65": ("Kiran (Bandra Works)", None), "P66": ("Omkar Bandra Works", None),
}
# chat_id: (name, is_group, participants (without ME), tie in the key or None)
CHATS = {
    "C01": ("Priya ❤️", False, ["P01"], ("person", "P01")),
    "C02": ("Ghar 🏡", True, ["P01", "P02", "P03", "P11", "P12", "P13"], ("organisation", "home")),
    "C03": ("Aarav", False, ["P02"], ("person", "P02")),
    "C04": ("Papa", False, ["P04"], ("person", "P04")),
    "C05": ("Mummy", False, ["P05"], ("person", "P05")),
    "C07": ("Shobha Mummyji", False, ["P06"], ("person", "P06")),
    "C08": ("Neha Didi", False, ["P07"], ("person", "P07")),
    "C09": ("Karan Jiju", False, ["P08"], ("person", "P08")),
    "C10": ("Sunil Chacha", False, ["P09"], ("person", "P09")),
    "C11": ("Rahul Arora", False, ["P10"], ("person", "P10")),
    "C12": ("Lakshmi", False, ["P11"], ("person", "P11")),
    "C13": ("Raju Driver", False, ["P12"], ("person", "P12")),
    "C14": ("Kamla Didi", False, ["P13"], ("person", "P13")),
    "C15": ("Alibaug House 🌴", True, ["P01", "P14", "P27"], ("organisation", "alibaug")),
    "C16": ("Bhola Alibaug", False, ["P14"], ("person", "P14")),
    "C17": ("Saffron Loop Core 🚚", True, ["P15", "P16", "P17"], ("organisation", "saffron")),
    "C18": ("SLL Ops Daily", True, ["P15", "P16", "P18", "P50", "P51", "P52"], ("organisation", "saffron")),
    "C19": ("Meghna Saffron", False, ["P15"], ("person", "P15")),
    "C20": ("Ankit Finance", False, ["P17"], ("person", "P17")),
    "C21": ("K&C Partners ☕", True, ["P19", "P21"], ("organisation", "kettle")),
    "C22": ("Zoya Khan", False, ["P19"], ("person", "P19")),
    "C23": ("Arora Textiles Accounts", True, ["P04", "P22"], ("organisation", "textiles")),
    "C24": ("Sandeep Freshkart", False, ["P23"], ("person", "P23")),
    "C25": ("Ritu Mehra", False, ["P24"], ("person", "P24")),
    "C26": ("Vikas BuildCo", False, ["P25"], ("person", "P25")),
    "C27": ("Gupta CA", False, ["P26"], ("person", "P26")),
    "C28": ("Shalini Interiors", False, ["P27"], ("person", "P27")),
    "C29": ("PixelPress Printers", False, ["P28"], ("person", "P28")),
    "C30": ("Ramesh AC", False, ["P29"], ("person", "P29")),
    "C31": ("Tapas Da Furniture", False, ["P30"], ("person", "P30")),
    "C32": ("Bandra Boys 🍻", True, ["P31", "P33", "P53", "P54"], None),
    "C33": ("Palm Grove B-Wing Residents", True, ["P36", "P37", "P61", "P62"], ("organisation", "society")),
    "C34": ("Greenwood 8B Parents", True, ["P55", "P56", "P57", "P58", "P59"], ("person", "P02")),
    "C35": ("Greenwood Annual Day Volunteers", True, ["P56", "P58", "P60"], ("organisation", "school")),
    "C36": ("Bandra Works Members", True, ["P35", "P65", "P66"], ("organisation", "cowork")),
    "C37": ("Rotary Club Bandra West", True, ["P39", "P63", "P64"], ("organisation", "rotary")),
    "C38": ("Dev Kapoor", False, ["P31"], ("person", "P31")),
    "C39": ("Ishaan", False, ["P32"], ("person", "P32")),
    "C40": ("Farhan", False, ["P33"], ("person", "P33")),
    "C41": ("Aditi Rao", False, ["P34"], ("person", "P34")),
    "C42": ("Coach Vinod", False, ["P42"], ("person", "P42")),
    "C43": ("Dr Shah Ortho", False, ["P43"], ("person", "P43")),
    "C44": ("Meenal Travels", False, ["P44"], ("person", "P44")),
    "C45": ("Juhu Flying Club", False, ["P45"], ("person", "P45")),
    "C46": ("Deepak Nair FleetX", False, ["P40"], ("person", "P40")),
    "C47": ("Japan 2027 🇯🇵", True, ["P01", "P07", "P08"], None),
    "C48": ("Mrs Kulkarni B-702", False, ["P37"], ("person", "P37")),
    "C49": ("Sana K&C", False, ["P21"], ("person", "P21")),
    "C50": ("Mehta ji", False, ["P22"], ("person", "P22")),
}
ORGS = [
    ("home", "Home", "residence", "home", "owner"),
    ("alibaug", "Alibaug house", "vacation home", "home", "owner"),
    ("society", "Palm Grove CHS", "society", "home", "resident"),
    ("school", "Greenwood High", "school", "home", "parent"),
    ("saffron", "Saffron Loop Logistics", "company", "work", "owner"),
    ("kettle", "Kettle & Crumb", "company", "work", "partner"),
    ("textiles", "Arora Textiles", "company", "work", "helper"),
    ("cowork", "Bandra Works", "workspace", "work", "member"),
    ("rotary", "Rotary Club Bandra West", "other", "home", "member"),
]
LINKS = {
    "P11": [("home", "supports")], "P12": [("home", "supports")], "P13": [("home", "supports")],
    "P14": [("alibaug", "supports")], "P36": [("society", "supports")], "P35": [("cowork", "supports")],
    "P51": [("saffron", "supports")],
    "P15": [("saffron", "runs")], "P16": [("saffron", "runs")], "P17": [("saffron", "runs")],
    "P18": [("saffron", "runs")], "P50": [("saffron", "runs")], "P52": [("saffron", "runs")],
    "P19": [("kettle", "runs")], "P21": [("kettle", "runs")],
    "P04": [("textiles", "runs")], "P22": [("textiles", "runs")],
}
LOOKS_AFTER = {"P12": ["P02", "P03"]}
SEED = {"circles": {"P01": "spouse", "P04": "parent", "P15": "colleague", "P19": "partner", "P23": "client",
                    "P26": "vendor", "P31": "friend", "P11": "staff", "P07": "sibling"},
        "organisations": ["Saffron Loop Logistics", "Kettle & Crumb"],
        "goals": [{"title": "Saffron Loop to 50 B2B clients by March", "area": "work", "type": "milestone",
                   "horizon": "1yr"}]}

MSGS = []  # (label, day, "HH:MM", chat, sender, body, kind, quote_label)


def m(label, day, hm, chat, sender, body, kind="text", q=None):
    MSGS.append((label, day, hm, chat, sender, body, kind, q))


# ------------------------------------------------------------------ goals (evidence) and early-week context
m("g_work1", 1, "10:05", "C17", "ME", "Team, target for this year is clear: 50 B2B clients on contract by March. We're at 31.")
m("g_work2", 15, "09:40", "C17", "ME", "Freshkart renewal puts us at 34. 16 more to hit 50 by March, let's keep pushing")
m("g_swim1", 2, "06:50", "C39", "ME", "Back in the pool from today. Plan is 3 mornings a week, Mon Wed Fri. Hold me to it 😅")
m(None, 2, "07:02", "C39", "P32", "Haha done. 6:30 at the club pool?")
m(None, 2, "07:03", "C39", "ME", "6:30 works")
m("g_swim2", 16, "07:45", "C39", "ME", "3 swims this week ✅ 40 laps today")
m(None, 16, "07:50", "C39", "P32", "Beast 💪")
m("g_japan1", 3, "21:10", "C47", "P01", "So are we finally doing Japan in April? Cherry blossom season 🌸")
m("g_bday1", 9, "22:30", "C08", "ME", "Didi, Priya turns 40 on 14 Nov. I want to plan a surprise party, need your help")
m(None, 9, "22:41", "C08", "P07", "Omg yes!! Let's do it at the Bandra rooftop place she likes")
m("g_bday2", 17, "13:15", "C41", "ME", "Aditi, keep 14 Nov evening free. Surprise for Priya's 40th, don't tell her 🤫")
m(None, 17, "13:30", "C41", "P34", "Sealed lips 🤐 so excited")
m("g_fin1", 4, "16:20", "C27", "ME", "Gupta ji, I want to build a 1 crore investment corpus in the next 3 years. Can you suggest how to split the SIPs?")
m(None, 4, "17:05", "C27", "P26", "Sure sir. With current savings rate it is doable. I will prepare a plan.")
m("g_fin2", 18, "11:30", "C27", "ME", "Started the 2 new SIPs as per your plan, 75k a month total. On track for the 1 cr target")
m("g_kids1", 5, "19:00", "C42", "ME", "Coach, how is Aarav doing? He really wants to make the U-14 district squad this season")
m(None, 5, "19:20", "C42", "P42", "Sir his batting is improving. Trials in January. If he keeps up the extra nets he has a good chance")
m("g_kids2", 19, "18:10", "C42", "ME", "Booked the extra Saturday nets for Aarav till December. District squad is the goal")
m("g_papa1", 6, "12:00", "C08", "ME", "Didi, Dr Shah says Papa's knee replacement should be done before Diwali, not later")
m(None, 6, "12:15", "C08", "P07", "Agreed. Papa keeps postponing. We have to push him")
m("g_papa2", 20, "20:05", "C04", "ME", "Papa, knee ka operation Diwali se pehle karwana hai. Main aur Didi saath rahenge, tension mat lo")
m(None, 20, "20:30", "C04", "P04", "Theek hai beta. Tum log jaise kaho")
m("g_home1", 7, "10:30", "C28", "ME", "Shalini, the brief is simple: Alibaug house fully renovated before next monsoon. Bathrooms, kitchen, deck.")
m(None, 7, "10:50", "C28", "P27", "Noted Nikhil. I'll phase it so the deck is done first")
m("g_home2", 21, "09:15", "C15", "ME", "Bhola, renovation starts next month. Everything has to be finished before the rains")
m("g_poker1", 8, "23:10", "C32", "ME", "Boys we need to make poker night a monthly thing again. First Saturday of every month?")
m(None, 8, "23:12", "C32", "P53", "Yesss finally")
m(None, 8, "23:15", "C32", "P54", "In 🃏")
m("g_poker2", 22, "22:00", "C32", "ME", "Reminder this is now a monthly fixture. No excuses 😂")
m("g_pilot1", 10, "15:00", "C45", "ME", "Hi, I'd like to start towards a private pilot licence. I know it'll take a few years alongside work, aiming to finish in 5")
m(None, 10, "15:40", "C45", "P45", "Welcome sir! Ground classes run Sat-Sun. Medical first, then we enrol you.")
m("g_pilot2", 23, "16:10", "C45", "ME", "Medical cleared ✅ Please enrol me for the November ground school batch")
m(None, 23, "16:30", "C45", "P45", "Done sir, you're enrolled for 7 Nov.")

# ------------------------------------------------------------------ early-week loops (context; not scored)
m("e1", 1, "11:00", "C24", "P23", "Nikhil, can you send the Q3 performance report for the Pune lanes?")
m("e1r", 1, "11:20", "C24", "ME", "Will send by tomorrow")
m("e1c", 2, "18:00", "C24", "ME", "Sent the Q3 report on mail, have a look")
m(None, 2, "18:30", "C24", "P23", "Got it thanks")
m("e2", 3, "09:30", "C02", "P01", "Kamla, kal bathroom ki deep cleaning karni hai")
m("e2r", 3, "09:35", "C02", "P13", "Ji didi")
m("e3", 4, "20:00", "C05", "P05", "Beta mera phone ka recharge khatam ho gaya")
m("e3r", 4, "20:02", "C05", "ME", "Abhi kar deta hoon Mummy")
m("e3c", 4, "20:10", "C05", "ME", "Ho gaya recharge, 3 months ka")
m("e4", 5, "15:00", "C29", "ME", "Need 200 Saffron Loop brochures for the logistics expo, by Thursday")
m("e4r", 5, "15:20", "C29", "P28", "ok sir, proof will share tomorrow")
m("e4c", 6, "12:00", "C29", "P28", "[photo] brochure proof", "image_caption")
m(None, 6, "12:30", "C29", "ME", "Approved, go ahead")
m("e5", 9, "10:00", "C17", "P17", "Nikhil, TDS payment due on 7th Oct, will need your approval on the bank portal")

# ------------------------------------------------------------------ scored window (days 14-27)
# L1 commitment ME, open -> assist (needs yes)
m("L1a", 14, "21:30", "C01", "P01", "Can we do Alibaug on 3rd Oct weekend? Kids are off. Book the ferry na")
m("L1b", 14, "21:34", "C01", "ME", "Yes let's do it. I'll book the ferry tickets")
m(None, 14, "21:35", "C01", "P01", "❤️")
# L2 commitment ME, done
m("L2a", 14, "10:15", "C04", "P04", "Beta, Dr Shah ka follow up appointment fix kar dena is hafte", "voice_transcript")
m("L2b", 14, "10:40", "C04", "ME", "Haan Papa, kal call karke fix karta hoon")
m("L2c", 15, "12:20", "C04", "ME", "Papa appointment fix ho gaya, Thursday 11 baje. Raju le jayega")
m(None, 15, "12:30", "C04", "P04", "👍")
# L3 commitment ME with due, done
m("L3a", 14, "11:00", "C17", "ME", "I'll send the revised pricing deck to Freshkart by Wednesday")
m(None, 14, "11:05", "C17", "P15", "👍 I'll share the lane costs with you tonight")
m("L3c", 16, "17:45", "C24", "ME", "Sandeep, sent you the revised pricing deck. Lane rates are on slide 6", "text")
m(None, 16, "18:10", "C24", "P23", "Thanks, will review with our team")
# L4 commitment ME, dropped by the society
m("L4a", 15, "19:00", "C33", "ME", "Joseph, I'll submit both parking sticker forms tomorrow")
m("L4c", 16, "10:30", "C33", "P36", "Sir no need now, committee has extended the date. Stickers will be issued in November only")
m(None, 16, "10:35", "C33", "ME", "Ok noted")
# L5 commitment ME, Bengali, open -> remind
m(None, 17, "14:00", "C31", "P30", "Dada, khater design ta pathalam. Dekhe janaben")
m(None, 17, "14:01", "C31", "P30", "[photo]", "image_caption")
m("L5a", 17, "15:10", "C31", "ME", "Bhalo hoyeche dada. Advance ta kal transfer kore debo, 25 hazar")
m(None, 17, "15:20", "C31", "P30", "Thik ache dada 🙏")
m(None, 24, "11:00", "C31", "P30", "Dada advance ta ki pathiyechen? Kaaj shuru korbo")
# L6 commitment ME, open -> assist (no yes needed: a private draft)
m("L6a", 18, "22:10", "C08", "P07", "Send me the guest list for Priya's party by Sunday so I can call the venue")
m("L6b", 18, "22:15", "C08", "ME", "Will send you the guest list by Sunday")
# L7 followup on a client, open -> assist (needs yes: a nudge leaves his phone)
m("L7a", 15, "16:00", "C25", "ME", "Ritu, any update on the signed PO for the Nashik route?")
m("L7b", 15, "16:40", "C25", "P24", "Finance is sitting on it. Will send by Friday for sure")
m(None, 19, "18:00", "C25", "ME", "Hi Ritu, gentle reminder on the PO")
m(None, 19, "19:30", "C25", "P24", "Yes yes, chasing them")
# L8 followup on CA, done via document
m("L8a", 16, "10:00", "C27", "ME", "Gupta ji, please send the advance tax computation for Q2")
m(None, 16, "10:30", "C27", "P26", "Sir by Monday")
m("L8c", 21, "11:15", "C27", "P26", "Advance_Tax_Q2_Nikhil.pdf", "document")
m(None, 21, "11:16", "C27", "P26", "Sir please check, amount payable before 15th")
m(None, 21, "12:00", "C27", "ME", "ok")
# L9 followup on vendor, not due yet -> leave (would annoy)
m("L9a", 24, "12:00", "C29", "ME", "Need 500 visiting cards for Tarun and Meghna, by next Thursday 8th")
m("L9b", 24, "12:30", "C29", "P28", "ok sir, will deliver to Bandra Works")
# L10 followup on AC repair, closed in the home group
m("L10a", 18, "09:00", "C30", "ME", "Ramesh, bedroom AC is leaking again. Can you come on Saturday?")
m(None, 18, "09:30", "C30", "P29", "Saturday 11 baje aata hoon sir")
m("L10c", 19, "13:40", "C02", "P13", "Bhaiya AC wala aaya tha, pipe badal diya. Ab paani nahi gir raha")
m(None, 19, "13:45", "C02", "P01", "👍👍")
# L11 commitment to a client, open -> remind
m("L11a", 22, "17:00", "C24", "P23", "Nikhil, can you share the SLA draft for the new Pune–Nashik lane? Legal wants it this week")
m("L11b", 22, "17:20", "C24", "ME", "Sure, will share by Thursday")
# L12 deadline ME, open -> remind
m("L12a", 23, "10:00", "C17", "P17", "GST filing for September is due on 20th Oct. I'll need your OTP approval on the portal that day")
m(None, 23, "10:05", "C17", "ME", "ok")
# L13 commitment ME in the school group, done
m("L13a", 15, "08:30", "C35", "P60", "Dear parents, volunteer forms for Annual Day must be submitted by 30 Sept")
m("L13b", 15, "09:10", "C35", "ME", "Count me in for the logistics team. Will submit the form")
m("L13c", 18, "21:00", "C35", "ME", "Submitted the form ✅")
m(None, 18, "21:05", "C35", "P60", "Thank you Mr Arora!")
# L14 deadline in the class group, open -> remind
m("L14a", 20, "09:00", "C34", "P56", "Reminder: Term 2 fees due on 5th October. Late fee after that 🙏")
m(None, 20, "09:10", "C34", "P55", "Thanks Anjali")
m(None, 20, "09:15", "C34", "P58", "🙏")
# L15 deadline from a client, closed by a colleague in another chat
m("L15a", 17, "12:00", "C26", "P25", "Nikhil ji, please send the September invoice before 25th so we can process it this month")
m(None, 17, "12:10", "C26", "ME", "Sure Vikas ji")
m("L15b", 17, "12:15", "C20", "ME", "Ankit pls raise the BuildCo September invoice before 25th")
m("L15c", 18, "16:00", "C20", "P17", "Done, sent to Vikas with the e-way bill copies")
# L16 question ME, open -> remind
m("L16a", 24, "18:00", "C22", "P19", "Should we take the second outlet in Khar at 1.8L rent? Broker needs an answer by next Friday")
m(None, 24, "18:30", "C22", "ME", "Let me look at the numbers")
# L17 question ME, answered -> done
m("L17a", 15, "20:00", "C01", "P01", "Aarav's birthday party, home or the play arena? Tell me tonight, I have to confirm")
m("L17c", 15, "21:30", "C01", "ME", "Arena. Less mess at home 😄 book kar do")
m(None, 15, "21:32", "C01", "P01", "Booked")
# L18 question ME, personal -> leave
m("L18a", 25, "19:00", "C03", "P02", "Papa can I go for Kunal's sleepover on Saturday?? Everyone is going")
m("L18b", 25, "19:20", "C03", "ME", "Let me talk to mumma first")
# L19 question ME, open -> assist (no yes needed: a private cost comparison)
m("L19a", 25, "11:00", "C17", "P15", "Diwali peak: do we hire 2 extra drivers or route the overflow through FleetX? Need your call by Monday")
m(None, 25, "11:20", "C17", "P16", "FleetX quoted 14/km last time")
# L20 question in Papa's business, answered -> done
m("L20a", 16, "15:00", "C23", "P22", "Nikhil beta, Surat godown lease renew karna hai. 2 saal ka karein ya 1 saal ka?")
m("L20c", 16, "18:30", "C23", "ME", "Mehta ji, 1 saal ka hi kijiye. Next year dekhenge")
m(None, 16, "18:35", "C23", "P04", "Theek hai")
# L21 staff commitment, open -> leave (staff handles it)
m("L21a", 26, "18:00", "C02", "P01", "Lakshmi kal guests aa rahe hain, paneer aur extra rotis bana dena")
m("L21b", 26, "18:05", "C02", "P11", "Ji didi")
# L22 staff commitment, done
m("L22a", 21, "08:00", "C02", "P12", "Sir aaj Myra baby ko 4 baje dance class le jaunga")
m("L22c", 21, "16:10", "C02", "P12", "Myra baby ko class pe chhod diya")
# L23 spouse commitment, open -> leave
m("L23a", 23, "20:00", "C01", "P01", "Kitchen sink is blocked again. I'll call the plumber tomorrow")
m(None, 23, "20:05", "C01", "ME", "ok thanks")
# L24 sister commitment, open -> leave
m("L24a", 22, "13:00", "C08", "P07", "I'll talk to Dr Shah's assistant about the OT date for Papa")
# L25 colleague commitment, open -> leave
m("L25a", 24, "10:00", "C18", "P16", "Will close the Bhiwandi warehouse rent renegotiation by Thursday")
m(None, 24, "10:05", "C18", "P50", "👍")
# L26 friend commitment, open -> leave
m("L26a", 25, "22:30", "C32", "P33", "Poker at mine on 3rd Oct. I'll arrange chips and food 🃏🍕")
m(None, 25, "22:31", "C32", "P31", "🔥")
# L27 vendor followup, done via image
m("L27a", 17, "17:00", "C15", "P27", "Will send the revised bathroom tile quotation by Monday")
m("L27c", 21, "12:30", "C15", "P27", "[photo] Revised quote - Italian matte tiles option", "image_caption")
# L28 colleague commitment, done
m("L28a", 15, "10:30", "C21", "P21", "I'll get the FSSAI licence renewal done this week")
m("L28c", 18, "17:00", "C21", "P21", "FSSAI renewed ✅ copy uploaded on drive")
m(None, 18, "17:05", "C21", "P19", "Super")
# L29 question from a cousin, dropped
m("L29a", 16, "21:00", "C11", "P10", "Bhai Lonavala trek on 27th? Let me know")
m(None, 16, "21:10", "C11", "ME", "Sounds good, let me check")
m("L29c", 24, "08:00", "C11", "P10", "Trek cancel bro, heavy rain alert for the weekend")
# L30 commitment ME, dropped
m("L30a", 19, "20:00", "C09", "ME", "Jiju, I'll send you the Japan visa checklist")
m("L30c", 20, "10:00", "C09", "P08", "No need, Meenal ji's office already sent us everything")
# L31 commitment ME, dropped by him
m("L31a", 18, "11:00", "C28", "ME", "Shalini, let's also redo the balcony railing in steel")
m("L31c", 25, "15:00", "C28", "ME", "Skip the railing for now, budget is getting tight. Bathrooms first")
m(None, 25, "15:20", "C28", "P27", "Understood")
# L32 question from the driver, "ok" does not close it -> assist (needs yes: booking a slot)
m("L32a", 22, "09:00", "C13", "P12", "Sir gaadi ki servicing due hai, kab bhejun service center?")
m(None, 22, "09:30", "C13", "ME", "ok")
# L33 commitment ME to his mother, open -> assist (needs yes to book)
m("L33a", 23, "21:00", "C05", "P05", "Beta Diwali pe Ludhiana aa rahe ho na sab? Tickets dekh lo jaldi, mehenge ho jayenge")
m("L33b", 23, "21:10", "C05", "ME", "Haan Mummy, dekhta hoon")
# L34 deadline ME, done with a document
m("L34a", 16, "13:00", "C44", "P44", "Sir please send passport copies of all 4 for the Japan visa file by 25 Sept")
m("L34c", 19, "10:00", "C44", "ME", "Passports_Arora_family.pdf", "document")
m(None, 19, "10:30", "C44", "P44", "Received sir, thank you")
# L35 commitment ME (voice note), open -> remind
m("L35a", 20, "11:00", "C04", "P04", "Beta bank wale ne KYC update maanga hai, tum online kar dena, mujhe nahi aata", "voice_transcript")
m("L35b", 20, "11:30", "C04", "ME", "Haan Papa, weekend pe kar dunga")
# L36 partner commitment, open -> leave
m("L36a", 26, "12:00", "C46", "P40", "Nikhil, I'll send over the revised revenue-share terms for the Diwali capacity by Tuesday")
m(None, 26, "12:10", "C46", "ME", "Great, thanks Deepak")
# L37 question from a neighbour, done
m("L37a", 19, "18:00", "C48", "P37", "Nikhil, can your driver drop my parcel to Andheri tomorrow? Only if he's free")
m("L37b", 19, "18:20", "C48", "ME", "Sure aunty, Raju will pick it at 10")
m("L37c", 20, "10:20", "C13", "P12", "Sir Kulkarni aunty ka parcel le liya, Andheri ja raha hoon")
# L38 commitment ME in rotary group, open -> remind
m("L38a", 22, "19:00", "C37", "P39", "Rotarians, please confirm your blood donation camp slot for 10 Oct")
m("L38b", 22, "19:30", "C37", "ME", "I'll take the 9am slot and bring 3 volunteers from the office")
# L39 staff asks him for leave, open -> remind (only he can say yes)
m("L39a", 26, "08:30", "C14", "P13", "Bhaiya agle mahine se 2 din chutti chahiye, gaon jaana hai. Theek hai?")
# L40 child voice note, commitment ME, done
m("L40a", 20, "19:00", "C02", "P03", "Papa aaj jaldi aaoge? Mujhe drawing dikhani hai", "voice_transcript")
m("L40b", 20, "19:05", "C02", "ME", "Haan beta, 7 baje tak aa jaunga")
m("L40c", 20, "19:10", "C02", "ME", "Pahunch gaya neeche 😊")

# ------------------------------------------------------------------ filler: ordinary chatter, no tasks
FILL = {
    "C01": [("P01", "Reached office?"), ("ME", "Yes"), ("P01", "😘"), ("ME", "Traffic is crazy today"),
            ("P01", "[photo]"), ("ME", "Haha cute"), ("P01", "Kids slept early today"), ("ME", "On my way"),
            ("P01", "Mom says hi"), ("ME", "❤️")],
    "C02": [("P11", "Didi aaj lauki ki sabzi bana di"), ("P01", "👍"), ("P12", "Sir gaadi neeche hai"),
            ("P13", "Didi main aa gayi"), ("P02", "[photo]"), ("P01", "Good morning everyone"), ("ME", "😂"),
            ("P12", "Aarav baba school pahunch gaye"), ("P11", "Didi doodh khatam ho gaya tha, le aayi")],
    "C03": [("P02", "Papa look [photo]"), ("ME", "Wow nice shot!"), ("P02", "We won the match 🏏"), ("ME", "Proud of you beta")],
    "C04": [("P04", "Good morning beta 🌞"), ("ME", "Good morning Papa"), ("P04", "[photo]"), ("ME", "🙏")],
    "C05": [("P05", "Jai Shri Krishna 🙏"), ("ME", "Jai Shri Krishna Mummy"), ("P05", "Khana kha liya?"), ("ME", "Haan")],
    "C07": [("P06", "Good morning beta, Priya ko bolna call kare"), ("ME", "Ji Mummyji"), ("P06", "🙏🌸")],
    "C08": [("P07", "😂😂 [video]"), ("ME", "Hahaha"), ("P07", "Mummy ki health theek hai na?"), ("ME", "Haan all good")],
    "C10": [("P09", "Happy Ganesh Chaturthi beta 🙏 Ganpati Bappa Morya"), ("ME", "Aapko bhi Chachaji 🙏")],
    "C12": [("P11", "Bhaiya kal 1 ghanta late aaungi"), ("ME", "Theek hai")],
    "C16": [("P14", "[photo]"), ("P14", "[photo]"), ("P14", "Sahab baarish bahut hai, sab theek hai"), ("ME", "👍"),
            ("P14", "[photo]"), ("P14", "Bijli aa gayi")],
    "C17": [("P16", "Daily numbers: 142 drops, 97% on time"), ("ME", "Great"), ("P15", "Freshkart volumes up 12% WoW"),
            ("P17", "Payment received from UrbanNest ✅"), ("ME", "👏"), ("P16", "Daily numbers: 151 drops, 95% on time"),
            ("P15", "Good call today with the Nashik team"), ("P16", "Daily numbers: 138 drops, 98% on time")],
    "C18": [("P50", "Bhiwandi: 3 trucks loaded"), ("P52", "Dispatch 8 done"), ("P51", "Sir gaadi MH04 Pune nikli"),
            ("P18", "Inventory count matched"), ("P50", "[photo]"), ("P52", "Dispatch 11 done"), ("P16", "👍"),
            ("P18", "Forklift back from repair"), ("P51", "Pune drop complete"), ("P50", "Bhiwandi: 5 trucks loaded")],
    "C19": [("P15", "Sent you the weekly MIS"), ("ME", "Thanks Meghna"), ("P15", "Call at 4?"), ("ME", "Done")],
    "C20": [("P17", "Bank balance as of today attached"), ("P17", "Balance_sheet_Aug.pdf"), ("ME", "Thanks")],
    "C21": [("P19", "Weekend sales 2.4L 🎉"), ("ME", "Superb"), ("P21", "New sourdough is a hit"), ("P21", "[photo]")],
    "C22": [("P19", "Saw the new menu boards? [photo]"), ("ME", "Looks great")],
    "C23": [("P22", "August ka hisaab bhej diya hai"), ("P04", "👍"), ("P22", "Payment from Surat party aa gaya")],
    "C32": [("P31", "Who's watching the match tonight?"), ("P53", "😂😂"), ("P54", "[video]"), ("ME", "Legendary"),
            ("P33", "Bro that six 🔥"), ("P31", "[photo]"), ("P53", "Happy birthday Kunal!! 🎂"), ("ME", "HBD bro 🎉"),
            ("P54", "Thanks guys ❤️")],
    "C33": [("P36", "Water supply will be off on Tuesday 10am-2pm for tank cleaning"), ("P61", "Noted"),
            ("P62", "Thanks Joseph"), ("P37", "Ganpati aarti at 8pm in the lobby 🙏"), ("P36", "Lift B under maintenance today")],
    "C34": [("P57", "Did anyone get the maths worksheet?"), ("P58", "[photo]"), ("P57", "Thanks Pooja!"),
            ("P59", "Is tomorrow a holiday?"), ("P56", "No, regular school"), ("P55", "🙏"), ("P58", "PTM photos [photo]")],
    "C35": [("P60", "Rehearsal schedule attached"), ("P60", "AnnualDay_Schedule.pdf"), ("P56", "Thank you Harsh")],
    "C36": [("P35", "Good morning members, coffee machine on 2nd floor fixed ☕"), ("P65", "Yay"),
            ("P35", "Parcel for Mr Arora at reception"), ("P66", "Anyone has an HDMI adapter?"), ("P35", "Wifi down for 10 min")],
    "C37": [("P63", "Great fellowship meeting yesterday 🙏"), ("P64", "[photo]"), ("P39", "Thank you all")],
    "C38": [("P31", "Bro check this [link]"), ("ME", "😂"), ("P31", "Lunch next week?"), ("ME", "Sure")],
    "C40": [("P33", "😂 [video]"), ("ME", "Hahaha")],
    "C41": [("P34", "Saw your post, congrats on the expo!"), ("ME", "Thanks Aditi!")],
    "C43": [("P43", "Clinic will be closed on Sunday")],
    "C46": [("P40", "Good meeting today Nikhil"), ("ME", "Likewise Deepak")],
    "C47": [("P07", "[photo] Kyoto in spring 😍"), ("P08", "Can't wait"), ("P01", "Need to start saving 😂")],
    "C49": [("P21", "Morning sales update: 38k"), ("ME", "👍")],
    "C50": [("P22", "Beta Papa ki dawai le li hai"), ("ME", "Thank you Mehta ji")],
}
for chat, lines in FILL.items():
    for sender, body in lines:
        for _ in range(rnd.choice((1, 2, 2, 3))):
            day = rnd.randrange(DAYS)
            hm = "%02d:%02d" % (rnd.randrange(8, 23), rnd.randrange(60))
            kind = "image_caption" if body.startswith("[photo]") and len(body) == 7 else (
                "document" if body.endswith(".pdf") else "text")
            m(None, day, hm, chat, sender, body, kind)
m("g_japan2", 3, "21:20", "C47", "ME", "Yes! Japan in April is locked. I'll start the visa paperwork with Meenal ji")
m("g_japan3", 16, "13:05", "C44", "ME", "Meenal ji, for the April Japan trip: Tokyo, Kyoto, Osaka. 10 nights, family of 4")

# ------------------------------------------------------------------ answer key
GOALS = [
    ("Saffron Loop to 50 B2B clients by March", "work", "milestone", "1yr", ["g_work1", "g_work2"]),
    ("Swim three mornings a week", "health", "habit", "3mo", ["g_swim1", "g_swim2"]),
    ("Family trip to Japan in April", "experiences", "experience", "1yr", ["g_japan1", "g_japan2", "g_japan3"]),
    ("Surprise party for Priya's 40th on 14 Nov", "spouse", "experience", "3mo", ["g_bday1", "g_bday2"]),
    ("Build a 1 crore investment corpus in 3 years", "finances", "milestone", "3yr", ["g_fin1", "g_fin2"]),
    ("Aarav makes the U-14 district cricket squad", "kids", "milestone", "1yr", ["g_kids1", "g_kids2"]),
    ("Papa's knee replacement before Diwali", "parents", "milestone", "3mo", ["g_papa1", "g_papa2"]),
    ("Renovate the Alibaug house before the monsoon", "home", "milestone", "1yr", ["g_home1", "g_home2"]),
    ("Monthly poker night with the Bandra boys", "friends", "habit", "1yr", ["g_poker1", "g_poker2"]),
    ("Earn a private pilot licence within 5 years", "self", "milestone", "5yr", ["g_pilot1", "g_pilot2"]),
]
LOOPS = [  # title, type, owner, chat, sources, due, status, closers, help, why
    ("Send the Q3 Pune report to Sandeep", "commitment", "ME", "C24", ["e1", "e1r"], None, "done", ["e1c"], None, ""),
    ("Kamla deep-cleans the bathroom", "commitment", "P13", "C02", ["e2", "e2r"], None, "open", [], None, ""),
    ("Recharge Mummy's phone", "commitment", "ME", "C05", ["e3", "e3r"], None, "done", ["e3c"], None, ""),
    ("PixelPress prints the expo brochures", "followup", "P28", "C29", ["e4", "e4r"], None, "done", ["e4c"], None, ""),
    ("Approve the TDS payment on 7 Oct", "deadline", "ME", "C17", ["e5"], "2026-10-07", "open", [], None, ""),
    ("Book the ferry for the Alibaug weekend", "commitment", "ME", "C01", ["L1b", "L1a"], "2026-10-03", "open", [],
     "assist", "Finding ferry slots is private; paying for the booking needs his yes."),
    ("Fix Papa's follow-up with Dr Shah", "commitment", "ME", "C04", ["L2b", "L2a"], None, "done", ["L2c"], None, ""),
    ("Send Freshkart the revised pricing deck", "commitment", "ME", "C17", ["L3a"], "2026-09-23", "done", ["L3c"], None, ""),
    ("Submit the parking sticker forms", "commitment", "ME", "C33", ["L4a"], None, "dropped", ["L4c"], None, ""),
    ("Transfer the 25k advance to Tapas Da", "commitment", "ME", "C31", ["L5a"], None, "open", [],
     "remind", "Only he can move the money; one reminder."),
    ("Send Didi the guest list for Priya's party", "commitment", "ME", "C08", ["L6b", "L6a"], "2026-09-27", "open", [],
     "assist", "A draft list from his contacts is private and reversible; no yes needed to prepare it."),
    ("Ritu sends the signed Nashik PO", "followup", "P24", "C25", ["L7a", "L7b"], None, "open", [],
     "assist", "Draft a polite nudge to the client; sending it needs his yes."),
    ("Gupta ji sends the Q2 advance tax computation", "followup", "P26", "C27", ["L8a"], None, "done", ["L8c"], None, ""),
    ("PixelPress delivers 500 visiting cards", "followup", "P28", "C29", ["L9a", "L9b"], "2026-10-08", "open", [],
     "leave", "The vendor confirmed and it isn't due yet; a nudge would only annoy."),
    ("Ramesh fixes the leaking bedroom AC", "followup", "P29", "C30", ["L10a"], None, "done", ["L10c"], None, ""),
    ("Share the Pune–Nashik SLA draft with Sandeep", "commitment", "ME", "C24", ["L11b", "L11a"], "2026-10-01", "open", [],
     "remind", "A legal document only he can send; remind him before Thursday."),
    ("Approve the September GST filing on 20 Oct", "deadline", "ME", "C17", ["L12a"], "2026-10-20", "open", [],
     "remind", "Needs his OTP on the day."),
    ("Submit the Annual Day volunteer form", "commitment", "ME", "C35", ["L13b", "L13a"], "2026-09-30", "done", ["L13c"], None, ""),
    ("Pay Aarav's term 2 school fees", "deadline", "ME", "C34", ["L14a"], "2026-10-05", "open", [],
     "remind", "A payment with a date; remind him the day before."),
    ("Raise the BuildCo September invoice", "deadline", "ME", "C26", ["L15a", "L15b"], "2026-09-25", "done", ["L15c"], None, ""),
    ("Decide on the second Kettle & Crumb outlet in Khar", "question", "ME", "C22", ["L16a"], "2026-10-09", "open", [],
     "remind", "Only he and Zoya can decide; one nudge before the broker's Friday."),
    ("Choose the venue for Aarav's birthday", "question", "ME", "C01", ["L17a"], None, "done", ["L17c"], None, ""),
    ("Answer Aarav about the sleepover", "question", "ME", "C03", ["L18a", "L18b"], None, "open", [],
     "leave", "A family call between him, Priya and Aarav; too personal for the assistant."),
    ("Decide extra drivers vs FleetX for Diwali", "question", "ME", "C17", ["L19a"], "2026-09-28", "open", [],
     "assist", "Build the cost comparison from the team's numbers; private, so no yes needed."),
    ("Decide the Surat godown lease term", "question", "ME", "C23", ["L20a"], None, "done", ["L20c"], None, ""),
    ("Lakshmi cooks for tomorrow's guests", "commitment", "P11", "C02", ["L21a", "L21b"], None, "open", [],
     "leave", "Priya asked the cook directly; staff handle it."),
    ("Raju takes Myra to dance class", "commitment", "P12", "C02", ["L22a"], None, "done", ["L22c"], None, ""),
    ("Priya calls the plumber for the sink", "commitment", "P01", "C01", ["L23a"], None, "open", [],
     "leave", "Priya took it; reminding him about his wife's task is not the assistant's place."),
    ("Neha fixes Papa's surgery date with Dr Shah's office", "commitment", "P07", "C08", ["L24a"], None, "open", [],
     "leave", "His sister owns it."),
    ("Tarun closes the Bhiwandi rent renegotiation", "commitment", "P16", "C18", ["L25a"], "2026-10-01", "open", [],
     "leave", "His colleague owns it and is on it."),
    ("Farhan hosts poker on 3 Oct", "commitment", "P33", "C32", ["L26a"], "2026-10-03", "open", [],
     "leave", "A friend's plan; nothing for the assistant to do."),
    ("Shalini sends the revised tile quotation", "followup", "P27", "C15", ["L27a"], None, "done", ["L27c"], None, ""),
    ("Sana renews the FSSAI licence", "commitment", "P21", "C21", ["L28a"], None, "done", ["L28c"], None, ""),
    ("Lonavala trek with Rahul on the 27th", "question", "ME", "C11", ["L29a"], "2026-09-27", "dropped", ["L29c"], None, ""),
    ("Send Jiju the Japan visa checklist", "commitment", "ME", "C09", ["L30a"], None, "dropped", ["L30c"], None, ""),
    ("Redo the Alibaug balcony railing", "commitment", "ME", "C28", ["L31a"], None, "dropped", ["L31c"], None, ""),
    ("Schedule the car service", "question", "ME", "C13", ["L32a"], None, "open", [],
     "assist", "Find a slot at the service centre; confirming it needs his yes."),
    ("Book Diwali tickets to Ludhiana", "commitment", "ME", "C05", ["L33b", "L33a"], None, "open", [],
     "assist", "Compare trains and flights privately; booking needs his yes."),
    ("Send passport copies for the Japan visa", "deadline", "ME", "C44", ["L34a"], "2026-09-25", "done", ["L34c"], None, ""),
    ("Update Papa's bank KYC online", "commitment", "ME", "C04", ["L35b", "L35a"], None, "open", [],
     "remind", "Needs his and Papa's credentials; a weekend reminder."),
    ("Deepak sends revised revenue-share terms", "commitment", "P40", "C46", ["L36a"], None, "open", [],
     "leave", "The partner owns it and isn't due yet."),
    ("Raju drops Mrs Kulkarni's parcel to Andheri", "commitment", "ME", "C48", ["L37b", "L37a"], None, "done", ["L37c"], None, ""),
    ("Bring 3 volunteers to the 9am blood camp slot", "commitment", "ME", "C37", ["L38b"], "2026-10-10", "open", [],
     "remind", "His own promise with a date; remind him before 10 Oct."),
    ("Answer Kamla about two days' leave", "question", "ME", "C14", ["L39a"], None, "open", [],
     "remind", "Only he can say yes to the leave; one reminder."),
    ("Come home early to see Myra's drawing", "commitment", "ME", "C02", ["L40b", "L40a"], None, "done", ["L40c"], None, ""),
]


def build(out_dir):
    rows = sorted(MSGS, key=lambda x: (x[1], x[2], x[0] or "~"))
    ids, msgs = {}, []
    for i, (label, day, hm, chat, sender, body, kind, q) in enumerate(rows, 1):
        hh, mm = map(int, hm.split(":"))
        ts = int((D0 + timedelta(days=day, hours=hh, minutes=mm, seconds=rnd.randrange(60))).timestamp())
        mid = "M%05d" % i
        if label:
            assert label not in ids, label
            ids[label] = mid
        name = ME_NAME if sender == "ME" else PEOPLE[sender][0]
        assert sender == "ME" or sender in CHATS[chat][2], (label, chat, sender)
        msgs.append({"id": mid, "chat_id": chat, "sender_id": sender, "sender_name": name, "ts": ts,
                     "kind": kind, "body": body, "quoted_id": ids.get(q) if q else None})
    chats = [{"chat_id": c, "name": n, "is_group": g, "participants": ["ME"] + p} for c, (n, g, p, _) in CHATS.items()]
    people = []
    for pid, (_, circle) in PEOPLE.items():
        if circle:
            row = {"id": pid, "circle": circle}
            if pid in LINKS:
                row["links"] = [{"organisation": o, "link": l} for o, l in LINKS[pid]]
            if pid in LOOKS_AFTER:
                row["looks_after"] = LOOKS_AFTER[pid]
            people.append(row)
    loops = []
    for title, typ, owner, chat, srcs, due, status, closers, help_, why in LOOPS:
        row = {"title": title, "type": typ, "owner": owner, "chat_id": chat, "source_msgs": [ids[s] for s in srcs],
               "due": due, "status": status, "closing_msgs": [ids[c] for c in closers]}
        if help_:
            row.update(help=help_, why=why)
        loops.append(row)
    answers = {
        "people": people,
        "organisations": [{"id": i, "name": n, "type": t, "side": s, "role": r} for i, n, t, s, r in ORGS],
        "chats": [{"chat_id": c, v[3][0]: v[3][1]} for c, v in CHATS.items() if v[3]],
        "goals": [{"title": t, "area": a, "type": ty, "horizon": h, "evidence": [ids[e] for e in ev]}
                  for t, a, ty, h, ev in GOALS],
        "open_loops": loops,
        "loops_scored_from": int((D0 + timedelta(days=SCORED_FROM_DAY)).timestamp()),
    }
    os.makedirs(os.path.join(out_dir, "answers"), exist_ok=True)
    with open(os.path.join(out_dir, "chats.jsonl"), "w", encoding="utf-8") as f:
        f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in chats)
    with open(os.path.join(out_dir, "messages.jsonl"), "w", encoding="utf-8") as f:
        f.writelines(json.dumps(x, ensure_ascii=False) + "\n" for x in msgs)
    json.dump(SEED, open(os.path.join(out_dir, "seed.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(answers, open(os.path.join(out_dir, "answers", "answers.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return chats, msgs, answers


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "synth")
    chats, msgs, ans = build(out)
    print("wrote %s: %d chats, %d messages, %d people in key, %d orgs, %d goals, %d loops"
          % (out, len(chats), len(msgs), len(ans["people"]), len(ans["organisations"]), len(ans["goals"]), len(ans["open_loops"])))
