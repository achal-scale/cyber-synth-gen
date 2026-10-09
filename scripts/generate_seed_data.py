"""
Generate realistic seed data: posts (10-20 per user), likes, reposts, replies,
follows, notifications, messages. Keeps existing users.json; overwrites other JSON files.
Run from backend: python3 scripts/generate_seed_data.py
"""
import json
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DATA_DIR = BACKEND_DIR / "seeds" / "data"

NUM_USERS = 100
MIN_POSTS_PER_USER = 10
MAX_POSTS_PER_USER = 20
MIN_FOLLOWS = 5
MAX_FOLLOWS = 35
MAX_LIKES_PER_POST = 50
REPOST_PROB = 0.12
MAX_REPLIES_PER_POST = 6
REPLY_PROB = 0.35
CONVOS_PER_USER = (0, 4)
MSGS_PER_CONVO = (1, 8)

POST_TEMPLATES = [
    "Just shipped a new feature. So grateful for the team. #build #ship",
    "Morning coffee and code. The best combo. #devlife #coding",
    "Hot take: {topic} What do you think? #discuss #tech",
    "Learning something new every day. Today: {topic}. #learning #growth",
    "Big announcement coming soon. Stay tuned. #announcement",
    "Thanks everyone for the support. It means a lot. #grateful",
    "Debugging at 2am. Who else? #developer #nightowl",
    "The future of {topic} is here. #innovation #future",
    "Quick tip: {tip} #tips #productivity",
    "Just hit a milestone. Couldn't have done it alone. #milestone #team",
    "Rethinking how we approach {topic}. #thoughts #design",
    "Weekend project: building something fun. #weekend #sideproject",
    "Interesting read on {topic}. Link in comments. #reading #learn",
    "That feeling when the tests finally pass. #testing #relief",
    "Discussion: what's your take on {topic}? #discuss #community",
    "Shoutout to @team for the great work this week. #teamwork",
    "New blog post: {topic}. Feedback welcome. #blog #writing",
    "Sometimes the best solution is the simplest one. #simplicity #code",
    "Excited to share what we've been working on. More soon. #excited",
    "The best part of remote work: {thing}. #remotework #life",
    "Throwback to when we launched. How far we've come. #throwback #growth",
    "Question for the community: {question}? #question #help",
    "Just discovered {thing}. Mind blown. #discovery #tech",
    "Proud of what we built. Here's how it works. #proud #build",
    "Hot weather today. Staying indoors with AC and code. #summer #coding",
    "Reminder: {reminder}. #reminder #productivity",
    "The amount of talent in this community is incredible. #community #talent",
    "Taking a break to recharge. Back soon. #break #wellness",
    "This is the way. #mandalorian #fun",
    "Real talk: {thought}. #realtalk #honest",
]

TOPICS = [
    "AI", "open source", "startups", "remote work", "product design",
    "developer experience", "APIs", "databases", "frontend", "backend",
    "testing", "DevOps", "cloud", "security", "performance",
]

HASHTAGS = [
    "AI", "TechNews", "coding", "devlife", "build", "ship", "tech",
    "innovation", "learning", "productivity", "community", "design",
]


def load_users():
    with open(DATA_DIR / "users.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return [u["id"] for u in data]

def gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"

def random_ts(base: datetime, days_back: int) -> str:
    d = base - timedelta(days=random.randint(0, days_back), hours=random.randint(0, 23), minutes=random.randint(0, 59))
    return d.strftime("%Y-%m-%dT%H:%M:%S")

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    base_ts = datetime.now(timezone.utc)
    days_back = 90

    user_ids = load_users()
    if len(user_ids) < NUM_USERS:
        raise SystemExit(f"Expected at least {NUM_USERS} users in users.json, got {len(user_ids)}")

    user_ids = user_ids[:NUM_USERS]
    random.shuffle(user_ids)

    # --- Posts (top-level first, then replies) ---
    posts = []
    post_id_counter = 1
    top_level_post_ids = []  # for replies, likes, reposts

    for uid in user_ids:
        n_posts = random.randint(MIN_POSTS_PER_USER, MAX_POSTS_PER_USER)
        for _ in range(n_posts):
            t = random.choice(POST_TEMPLATES)
            content = t.replace("{topic}", random.choice(TOPICS)).replace("{tip}", "always read the docs").replace("{thing}", "flexible schedule").replace("{question}", "best practices").replace("{thought}", "consistency beats intensity").replace("{reminder}", "back up your work")
            if random.random() < 0.4:
                content += " " + " #" + random.choice(HASHTAGS)
            pid = f"post-{post_id_counter}"
            post_id_counter += 1
            posts.append({
                "id": pid,
                "author_id": uid,
                "content": content,
                "created_at": random_ts(base_ts, days_back),
            })
            top_level_post_ids.append(pid)

    # Replies
    for post in list(posts):
        if random.random() > REPLY_PROB:
            continue
        n_replies = random.randint(1, MAX_REPLIES_PER_POST)
        reply_templates = [
            "Great point. I agree.",
            "Thanks for sharing this.",
            "Hadn't thought of it that way.",
            "Same here. Experienced this recently.",
            "Could you elaborate on that?",
            "This is so true.",
            "Adding this to my list.",
        ]
        for _ in range(n_replies):
            reply_author = random.choice(user_ids)
            pid = f"post-{post_id_counter}"
            post_id_counter += 1
            posts.append({
                "id": pid,
                "author_id": reply_author,
                "content": random.choice(reply_templates) + (" #" + random.choice(HASHTAGS) if random.random() < 0.3 else ""),
                "created_at": random_ts(base_ts, days_back),
                "parent_post_id": post["id"],
            })

    # --- Follows ---
    follows = []
    for i, uid in enumerate(user_ids):
        n = random.randint(MIN_FOLLOWS, MAX_FOLLOWS)
        candidates = [u for u in user_ids if u != uid]
        random.shuffle(candidates)
        for j in range(min(n, len(candidates))):
            other = candidates[j]
            follows.append({
                "id": gen_id("follow"),
                "follower_id": uid,
                "following_id": other,
                "created_at": random_ts(base_ts, days_back),
            })

    # --- Likes (only top-level posts) ---
    likes = []
    for pid in top_level_post_ids:
        n_likes = random.randint(0, min(MAX_LIKES_PER_POST, len(user_ids)))
        likers = random.sample(user_ids, n_likes)
        for uid in likers:
            likes.append({
                "id": gen_id("like"),
                "user_id": uid,
                "post_id": pid,
                "created_at": random_ts(base_ts, days_back),
            })

    # --- Reposts ---
    reposts = []
    for pid in top_level_post_ids:
        if random.random() > REPOST_PROB:
            continue
        n_reposts = random.randint(1, min(5, len(user_ids)))
        reposters = random.sample(user_ids, n_reposts)
        for uid in reposters:
            reposts.append({
                "id": gen_id("repost"),
                "user_id": uid,
                "post_id": pid,
                "created_at": random_ts(base_ts, days_back),
            })

    # --- Notifications (for likes, reposts, follows, replies) ---
    notifications = []
    # Follow notifications (recipient = followed user)
    for f in follows:
        notifications.append({
            "id": gen_id("notif"),
            "recipient_id": f["following_id"],
            "actor_id": f["follower_id"],
            "type": "follow",
            "created_at": f["created_at"],
            "read": random.random() < 0.5,
        })
    # Like notifications
    for like in likes[:2000]:  # cap to avoid huge file
        post = next((p for p in posts if p["id"] == like["post_id"]), None)
        if not post:
            continue
        if post["author_id"] != like["user_id"]:
            notifications.append({
                "id": gen_id("notif"),
                "recipient_id": post["author_id"],
                "actor_id": like["user_id"],
                "type": "like",
                "post_id": like["post_id"],
                "created_at": like["created_at"],
                "read": random.random() < 0.5,
            })
    # Reply notifications
    for post in posts:
        if "parent_post_id" not in post:
            continue
        parent = next((p for p in posts if p["id"] == post["parent_post_id"]), None)
        if parent and parent["author_id"] != post["author_id"]:
            notifications.append({
                "id": gen_id("notif"),
                "recipient_id": parent["author_id"],
                "actor_id": post["author_id"],
                "type": "reply",
                "post_id": post["id"],
                "created_at": post["created_at"],
                "read": random.random() < 0.5,
            })

    # --- Messages ---
    messages = []
    msg_id = 1
    convos = []
    for uid in user_ids:
        n_convos = random.randint(*CONVOS_PER_USER)
        others = [u for u in user_ids if u != uid]
        random.shuffle(others)
        for k in range(min(n_convos, len(others))):
            other = others[k]
            pair = tuple(sorted([uid, other]))
            if pair in convos:
                continue
            convos.append(pair)
            n_msgs = random.randint(*MSGS_PER_CONVO)
            bodies = [
                "Hey, how are you?",
                "Thanks for the post, really helped.",
                "We should connect sometime.",
                "Quick question about your last update.",
                "Got it, thanks!",
                "Let me know when you're free.",
                "Sounds good to me.",
                "I'll check it out.",
            ]
            for m in range(n_msgs):
                sender = uid if m % 2 == 0 else other
                recipient = other if sender == uid else uid
                messages.append({
                    "id": f"msg-{msg_id}",
                    "sender_id": sender,
                    "recipient_id": recipient,
                    "content": random.choice(bodies),
                    "created_at": random_ts(base_ts, days_back),
                    "read": m < n_msgs - 1 or random.random() < 0.5,
                })
                msg_id += 1

    # --- Write ---
    def write_json(name: str, data: list) -> None:
        path = DATA_DIR / name
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Wrote {len(data)} items to {path}")

    write_json("posts.json", posts)
    write_json("follows.json", follows)
    write_json("likes.json", likes)
    write_json("reposts.json", reposts)
    write_json("notifications.json", notifications)
    write_json("messages.json", messages)

    # Update trends to include more hashtags (counts will be computed at runtime)
    trends = [
        {"id": "trend-1", "name": "#AI", "post_count": 0, "created_at": "2024-01-01T00:00:00", "updated_at": base_ts.strftime("%Y-%m-%dT%H:%M:%S")},
        {"id": "trend-2", "name": "#TechNews", "post_count": 0, "created_at": "2024-01-01T00:00:00", "updated_at": base_ts.strftime("%Y-%m-%dT%H:%M:%S")},
        {"id": "trend-3", "name": "#coding", "post_count": 0, "created_at": "2024-01-01T00:00:00", "updated_at": base_ts.strftime("%Y-%m-%dT%H:%M:%S")},
        {"id": "trend-4", "name": "#devlife", "post_count": 0, "created_at": "2024-01-01T00:00:00", "updated_at": base_ts.strftime("%Y-%m-%dT%H:%M:%S")},
        {"id": "trend-5", "name": "#build", "post_count": 0, "created_at": "2024-01-01T00:00:00", "updated_at": base_ts.strftime("%Y-%m-%dT%H:%M:%S")},
    ]
    write_json("trends.json", trends)

    print(f"Done. Posts: {len(posts)} (top-level: {len(top_level_post_ids)}), likes: {len(likes)}, reposts: {len(reposts)}, follows: {len(follows)}, notifications: {len(notifications)}, messages: {len(messages)}")

if __name__ == "__main__":
    main()
