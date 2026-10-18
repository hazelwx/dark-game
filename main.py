# -*- coding: utf-8 -*-
import os
import random
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn

# ==============================================================================
# 1. 《暗夜进化》核心游戏逻辑
# ==============================================================================
MAX_PLAYERS = 6
ALL_ROLES = ["🔪 猎手 (高攻)", "🐇 食草 (高速)", "🐒 灵长 (均衡)", "🐺 独狼 (随机)"]

DARK_EVENTS = [
    {"name": "血月当空", "desc": "血月之力涌动，本回合所有伤害 +50%！", "effect": "dmg_boost"},
    {"name": "迷雾笼罩", "desc": "暗夜迷雾弥漫，本回合所有绝杀被封印！", "effect": "no_ult"},
    {"name": "进化潮汐", "desc": "暗夜能量暴涨，所有存活者 +3 进化点！", "effect": "evo_gift"},
    {"name": "暗夜瘟疫", "desc": "瘟疫蔓延，所有存活者损失 15 HP！", "effect": "plague"},
    {"name": "血月回响", "desc": "暗夜低语穿越生死，一名逝者被唤回！", "effect": "revive"},
]

def create_player(name, role):
    if "猎手" in role:
        p = {'name': name, 'role': role, 'atk': 9, 'def': 4, 'spd': 3, 'hp': 100, 'evo': 3, 'alive': True, 'defending': False}
    elif "食草" in role:
        p = {'name': name, 'role': role, 'atk': 2, 'def': 3, 'spd': 9, 'hp': 100, 'evo': 3, 'alive': True, 'defending': False}
    elif "灵长" in role:
        p = {'name': name, 'role': role, 'atk': 6, 'def': 6, 'spd': 6, 'hp': 100, 'evo': 4, 'alive': True, 'defending': False}
    else:
        p = {'name': name, 'role': role, 'atk': 7, 'def': 5, 'spd': 6, 'hp': 100, 'evo': 5, 'alive': True, 'defending': False}
    p['no_ult_until'] = 0
    return p

def pick_random_role(players):
    return random.choice(ALL_ROLES)

class DarkEvolutionGame:
    def __init__(self):
        self.players = []
        self.turn = 1
        self.game_over = False
        self.actions_this_round = {}

    def reset(self, player_names_with_roles):
        self.players = []
        self.turn = 1
        self.game_over = False
        self.actions_this_round = {}
        for name, role_name in player_names_with_roles:
            self.players.append(create_player(name, role_name))

    def get_alive_players(self):
        return [p for p in self.players if p['alive']]

    def submit_action(self, player_name, action_data):
        if player_name not in [p['name'] for p in self.get_alive_players()]:
            return False, "你已经被暗夜淘汰了！"
        self.actions_this_round[player_name] = action_data
        return True, "行动已潜伏提交！"

    def check_and_execute_round(self):
        alive_players = self.get_alive_players()
        if len(self.actions_this_round) < len(alive_players):
            return False, "等待暗夜中的其他猎食者行动..."

        logs = []
        event_effect = None

        for p in alive_players:
            p['evo'] += 1
        logs.append("🌙 暗夜能量涌动，所有存活者获得 1 点基础进化点！")

        if self.turn % 3 == 0:
            event = random.choice(DARK_EVENTS)
            logs.append(f"🌑 暗夜事件：【{event['name']}】{event['desc']}")
            event_effect = event['effect']

            if event_effect == 'evo_gift':
                for p in self.get_alive_players():
                    p['evo'] += 3
                logs.append("✨ 暗夜能量涌入，所有存活者获得 3 进化点！")

            elif event_effect == 'plague':
                for p in list(self.get_alive_players()):
                    p['hp'] -= 15
                    if p['hp'] <= 0:
                        p['hp'] = 0
                        p['alive'] = False
                        logs.append(f"☠️ {p['name']} 被瘟疫吞噬！")
                    else:
                        logs.append(f"🦠 {p['name']} 受到 15 点瘟疫伤害（剩余 {p['hp']} HP）")

            elif event_effect == 'revive':
                dead_players = [p for p in self.players if not p['alive']]
                if dead_players:
                    revived = random.choice(dead_players)
                    revived['alive'] = True
                    revived['hp'] = 30
                    revived['evo'] = 0
                    revived['defending'] = False
                    revived['no_ult_until'] = self.turn + 1
                    logs.append(f"🕯️ 暗夜低语穿越生死，{revived['name']} 被唤回！以 30 HP 复活，且下回合无法发动绝杀。")
                else:
                    logs.append("🕯️ 暗夜低语回荡，但无人可归……")

            alive_players = self.get_alive_players()

        action_list = []
        for p in alive_players:
            act = self.actions_this_round.get(p['name'])
            if act:
                action_list.append((p, act))

        action_list.sort(key=lambda x: x[0]['spd'], reverse=True)

        for actor, action in action_list:
            if not actor['alive']:
                continue
            act_type = action['type']

            if act_type == 'ult':
                if event_effect == 'no_ult':
                    logs.append(f"🌫️ {actor['name']} 试图发动绝杀，但迷雾封印了绝杀之力！")
                    continue
                if actor.get('no_ult_until', 0) >= self.turn:
                    logs.append(f"⚠️ {actor['name']} 尚未从复活的虚弱中恢复，无法绝杀！")
                    continue

                target = next((p for p in alive_players if p['name'] == action['target']), None)
                if not target or not target['alive']:
                    continue

                if actor['evo'] >= 6:
                    actor['evo'] -= 6
                    base_damage = 30 + actor['atk']*2
                    damage = base_damage
                    
                    if event_effect == 'dmg_boost':
                        damage = int(damage * 1.5)
                    logs.append(f"🔥 {actor['name']} 消耗 6 进化点发动【暗夜绝杀】！对 {target['name']} 造成 {damage} 点无视防御的绝对伤害！")
                    target['hp'] -= damage
                    if target['hp'] <= 0:
                        target['alive'] = False
                        logs.append(f"💀 {target['name']} 被暗夜彻底吞噬！")
                    else:
                        logs.append(f"😰 {target['name']} 绝地求生，剩余 HP 为 {target['hp']}")
                else:
                    logs.append(f"⚠️ {actor['name']} 想要发动绝杀，但进化点不足 6 点，白白浪费了一次出手！")

            elif act_type == 'attack' and action.get('target'):
                target = next((p for p in alive_players if p['name'] == action['target']), None)
                if target and target['alive']:
                    base_damage = int(actor['atk'] * 2.5)
                    target_defense = target['def'] * (2 if target['defending'] else 1)
                    damage = base_damage - target_defense
                    damage = max(1, damage)

                    is_crit = False
                    if actor['spd'] > target['spd']:
                        crit_chance = 0.2 + (actor['spd'] - target['spd']) * 0.05
                        if random.random() < crit_chance:
                            is_crit = True
                            damage = int(damage * 1.5)

                    if event_effect == 'dmg_boost':
                        damage = int(damage * 1.5)

                    crit_text = " 💥【暴击】" if is_crit else ""
                    if target['defending']:
                        logs.append(f"🛡️ {target['name']} 成功防御！{actor['name']} 的攻击仍造成 {damage} 点伤害{crit_text}")
                        target['defending'] = False
                    else:
                        logs.append(f"⚔️ {actor['name']} 对 {target['name']} 发动猎杀！造成 {damage} 点伤害{crit_text}")

                    target['hp'] -= damage
                    if target['hp'] <= 0:
                        target['alive'] = False
                        logs.append(f"💀 {target['name']} 被暗夜彻底吞噬！")
                    else:
                        logs.append(f"😰 {target['name']} 绝地求生，剩余 HP 为 {target['hp']}")

            elif act_type == 'defend':
                actor['defending'] = True
                logs.append(f"🛡️ {actor['name']} 蛰伏在暗夜中，进入防御姿态！")
            elif act_type == 'evolve' and actor['evo'] >= 2:
                actor['evo'] -= 2
                actor['atk'] += 2
                actor['def'] += 2
                actor['spd'] += 2
                logs.append(f"🧬 {actor['name']} 消耗 2 进化点，暗夜血脉觉醒，全属性 +2！")
            elif act_type == 'rest' and actor['evo'] >= 1:
                actor['evo'] -= 1
                recover = int(actor['hp'] * 0.5)
                actor['hp'] = min(100, actor['hp'] + recover)
                logs.append(f"💤 {actor['name']} 消耗 1 进化点，汲取暗夜能量，恢复 {recover} HP！")

        self.turn += 1
        self.actions_this_round = {}
        return True, logs


app = FastAPI()
room_games = {}
room_connections = {}

@app.get("/")
async def get():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>暗夜进化 联机版</title>
    <style>
        * { box-sizing: border-box; }
        body {
            margin: 0; padding: 20px; background-color: #08080e;
            background-image: 
                radial-gradient(ellipse at 30% 30%, rgba(80, 60, 120, 0.15) 0%, transparent 70%),
                radial-gradient(ellipse at 80% 70%, rgba(60, 80, 120, 0.1) 0%, transparent 60%);
            color: #e0e0e0; font-family: 'Inter', sans-serif;
            min-height: 100vh; display: flex; justify-content: center; align-items: center;
        }
        #stars { position: fixed; top: 0; left: 0; width: 1px; height: 1px; pointer-events: none; z-index: 0; animation: twinkle 5s infinite alternate; }
        @keyframes twinkle { 0% { opacity: 0.3; } 100% { opacity: 1; } }

        #app-container {
            position: relative; z-index: 1; width: 100%; max-width: 1100px; min-height: 600px;
            background: rgba(20, 20, 28, 0.75); backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 20px; padding: 25px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.9);
        }
        h1 { text-align: center; margin: 0 0 15px 0; font-size: 2.5rem; font-weight: 700; background: linear-gradient(135deg, #bb86fc, #00e5ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }

        .rules-grid {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 10px; margin-bottom: 20px; background: rgba(28, 28, 35, 0.6); border-radius: 12px; padding: 15px;
        }
        .rule-item { background: rgba(0, 0, 0, 0.3); padding: 10px 12px; border-radius: 6px; border-left: 3px solid #444; }
        .rule-item h4 { margin: 0 0 5px 0; font-size: 14px; color: #fff; }
        .rule-item div { font-size: 12px; color: #aaa; }
        .text-gold { color: #ffd700; }
        .text-red { color: #ff6b6b; }
        .text-cyan { color: #22d3ee; }
        .text-green { color: #69db7c; }

        #lobby { text-align: center; max-width: 420px; margin: 40px auto 0; }
        #lobby input { background: rgba(0,0,0,0.5); border: 1px solid #444; color: #fff; padding: 12px 15px; border-radius: 8px; width: 100%; margin-bottom: 12px; outline: none; font-size: 16px; }
        #lobby input:focus { border-color: #bb86fc; box-shadow: 0 0 12px rgba(187, 134, 252, 0.2); }
        
        .btn-primary { background: linear-gradient(135deg, #bb86fc, #9b5de5); color: #000; border: none; padding: 12px 0; width: 100%; font-weight: bold; font-size: 18px; border-radius: 8px; cursor: pointer; transition: all 0.2s; }
        .btn-primary:hover { box-shadow: 0 0 20px rgba(187, 134, 252, 0.4); }

        .random-role-box { background: rgba(187, 134, 252, 0.08); border: 1px dashed rgba(187, 134, 252, 0.35); padding: 12px 15px; border-radius: 8px; margin-bottom: 14px; text-align: center; }
        .random-role-box .title { color: #bb86fc; font-size: 14px; font-weight: 600; margin-bottom: 4px; letter-spacing: 1px; }
        .random-role-box .desc { color: #888; font-size: 12px; }

        #game { display: none; }
        #status { text-align: center; color: #bb86fc; font-weight: 500; margin: 10px 0; }
        #btn_leave { display: block; margin: 0 auto 12px; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.15); color: #999; padding: 6px 14px; border-radius: 6px; font-size: 12px; cursor: pointer; transition: all .2s; }
        #btn_leave:hover { color: #ff6b6b; border-color: #ff6b6b; }

        #game-area { position: relative; width: 100%; height: 450px; margin-bottom: 15px; }
        #round-table-bg {
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
            width: 420px; height: 420px; background: radial-gradient(circle at center, rgba(30, 20, 50, 0.4) 0%, rgba(10, 10, 16, 0.8) 40%, rgba(0, 0, 0, 0.9) 80%);
            border: 1px solid rgba(187, 134, 252, 0.1); border-radius: 50%;
            box-shadow: 0 0 30px rgba(187, 134, 252, 0.05), inset 0 0 40px rgba(0,0,0,0.8), 0 0 60px rgba(100, 80, 160, 0.2);
            display: flex; justify-content: center; align-items: center; color: rgba(255,255,255,0.08); font-size: 16px; letter-spacing: 8px; font-weight: bold;
        }
        #round-table-bg::before { content: ''; position: absolute; top: 2px; left: 2px; right: 2px; bottom: 2px; border-radius: 50%; border: 1px solid rgba(187, 134, 252, 0.15); }
        #round-table-bg::after { content: ''; position: absolute; top: 15px; left: 15px; right: 15px; bottom: 15px; border-radius: 50%; border: 1px dashed rgba(187, 134, 252, 0.05); }

        .player-card {
            position: absolute; width: 150px; background: rgba(30, 30, 40, 0.9); backdrop-filter: blur(4px);
            border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 8px 12px;
            box-shadow: 0 8px 25px rgba(0,0,0,0.8); transition: all 0.2s ease; z-index: 2;
            transform: translate(-50%, -50%);
        }
        .player-card:hover { border-color: #bb86fc; box-shadow: 0 0 25px rgba(187, 134, 252, 0.4); }
        .card-header { display: flex; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 6px; margin-bottom: 6px; }
        .card-name { font-weight: bold; font-size: 16px; color: #fff; }
        .card-role { font-size: 12px; color: #bb86fc; }
        .card-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 8px; font-size: 12px; }
        .stat-item { display: flex; justify-content: space-between; }
        .stat-label { color: #888; }
        .stat-val { font-weight: 600; }
        .stat-val.atk { color: #ff6b6b; } .stat-val.def { color: #22d3ee; } .stat-val.spd { color: #69db7c; }
        .stat-val.hp { color: #ffd700; } .stat-val.evo { color: #bb86fc; }
        .card-dead { opacity: 0.3; filter: grayscale(1); text-decoration: line-through; }
        .card-dead:hover { transform: none; border-color: #444; }

        #logs { height: 120px; overflow-y: auto; padding: 12px 15px; background: rgba(0,0,0,0.4); border-radius: 8px; font-family: monospace; font-size: 13px; color: #0f0; line-height: 1.5; margin: 15px 0; border: 1px solid rgba(255,255,255,0.05); }

        #actions { display: none; background: rgba(0,0,0,0.3); border-radius: 10px; padding: 15px; border: 1px solid #444; }
        .action-buttons { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; }
        .btn-action { flex: 1 1 80px; max-width: 120px; padding: 8px 0; font-size: 14px; background: rgba(28, 28, 36, 0.8); border: 1px solid #444; border-radius: 6px; color: #fff; cursor: pointer; }
        .btn-attack { border-left: 4px solid #ff6b6b; }
        .btn-defend { border-left: 4px solid #22d3ee; }
        .btn-evolve { border-left: 4px solid #bb86fc; }
        .btn-rest { border-left: 4px solid #69db7c; }
        .btn-ult { border-left: 4px solid #ffd700; font-weight: bold; background: rgba(60, 50, 30, 0.5); color: #ffd700; }
        .btn-ult:hover:not(:disabled) { background: rgba(255, 215, 0, 0.2); }
        .btn-ult:disabled { opacity: 0.5; cursor: not-allowed; filter: grayscale(1); }
        .btn-action:hover:not(:disabled) { transform: scale(1.05); }

        #targets_box { display: none; margin-top: 15px; padding-top: 15px; border-top: 1px solid rgba(255,255,255,0.1); text-align: center; }
        .target-btn { background: #ff6b6b; border: 1px solid #ff6b6b; color: #000; padding: 8px 15px; border-radius: 6px; margin: 5px; cursor: pointer; font-weight: bold; }

        #restart_container { display: none; text-align: center; padding: 15px; }
        .btn-restart { background: #ffd700; color: #000; border: none; padding: 12px 30px; font-weight: bold; font-size: 16px; border-radius: 8px; cursor:pointer; box-shadow: 0 0 20px rgba(255, 215, 0, 0.3); }
        
        .death-toast, .revive-toast {
            position: fixed; top: -100px; left: 50%; transform: translateX(-50%);
            border: 3px solid #ffd700; padding: 20px 40px; border-radius: 12px;
            color: #fff; font-weight: bold; font-size: 28px; z-index: 999; pointer-events: none; white-space: nowrap;
            animation: popupDeath 2s forwards;
        }
        .death-toast { background: rgba(255, 0, 0, 0.9); text-shadow: 0 0 20px rgba(255,0,0,0.8); box-shadow: 0 0 40px rgba(255, 0, 0, 0.6); }
        .revive-toast { background: linear-gradient(135deg, rgba(187,134,252,0.95), rgba(100,80,180,0.95)); text-shadow: 0 0 20px rgba(187,134,252,0.8); box-shadow: 0 0 40px rgba(187, 134, 252, 0.6); }
        @keyframes popupDeath {
            0% { top: -100px; opacity: 0; transform: translateX(-50%) scale(0.8); }
            20% { top: 50px; opacity: 1; transform: translateX(-50%) scale(1.2); }
            40% { top: 30px; transform: translateX(-50%) scale(0.95); }
            60% { top: 40px; transform: translateX(-50%) scale(1); }
            100% { top: 40px; opacity: 0; transform: translateX(-50%) scale(1); }
        }
        
        @media (max-width: 768px) {
            #app-container { padding: 15px; }
            #game-area { height: 400px; }
            #round-table-bg { width: 300px; height: 300px; font-size: 12px; }
            .player-card { width: 140px; padding: 8px 10px; font-size: 12px; }
            .action-buttons { flex-direction: column; }
            .btn-action { max-width: 100%; }
            .death-toast, .revive-toast { font-size: 18px; padding: 15px 20px; white-space: normal; width: 80%; }
        }
    </style>
    </head>
    <body>
    <div id="stars"></div>
    <div id="app-container">
        <h1>🌙 暗夜进化</h1>

        <div class="rules-grid">
            <div class="rule-item" style="border-left-color: #bb86fc;">
                <h4>🎭 职业天赋 (允许重复)</h4>
                <div>猎手(高攻) / 食草(高速)<br>灵长(均衡) / 独狼(随机)</div>
            </div>
            <div class="rule-item" style="border-left-color: #ff6b6b;">
                <h4>🗡️ 猎杀</h4>
                <div>消耗 <b class="text-gold">1</b> 进化点。<br>伤害 = <b class="text-red">攻击 × 2.5</b> - 防御<br>速度高于目标时有概率暴击</div>
            </div>
            <div class="rule-item" style="border-left-color: #22d3ee;">
                <h4>🛡️ 防御</h4>
                <div>不消耗进化点。<br>本回合 <b class="text-cyan">防御力翻倍</b>，极强保命</div>
            </div>
            <div class="rule-item" style="border-left-color: #69db7c;">
                <h4>🧬 进化 / 💤 休养</h4>
                <div>进化：消耗 <b class="text-gold">2</b> 点，<b class="text-green">全属性+2</b><br>休养：消耗 <b class="text-gold">1</b> 点，恢复 <b class="text-green">50%</b>生命</div>
            </div>
            <div class="rule-item" style="border-left-color: #ffd700; grid-column: 1 / -1;">
                <h4>🔥 暗夜绝杀 (全新终结技)</h4>
                <div>消耗 <b class="text-gold">6</b> 进化点。造成 <b class="text-red">30 + 攻击力×2</b> 的无视防御绝对伤害！</div>
            </div>
            <div class="rule-item" style="border-left-color: #ff00ff; grid-column: 1 / -1;">
                <h4>🌑 暗夜事件 (每 3 回合随机触发)</h4>
                <div>血月当空(伤害+50%) / 迷雾笼罩(封印绝杀) / 进化潮汐(全体+3进化点)<br>
                暗夜瘟疫(全体-15HP) / <b class="text-gold">血月回响(随机复活一名逝者，30HP，下回合禁绝杀)</b></div>
            </div>
            <div class="rule-item" style="border-left-color: #ffd700; grid-column: 1 / -1; margin-top: -5px; border-color:#666; background:rgba(0,0,0,0.15);">
                <h4 style="color:#aaa;">🤫 暗夜诡计</h4>
                <div style="color:#aaa;"><b class="text-gold">核心机制：</b>第1回合公开真实属性。从<b class="text-red">第2回合起</b>，其他人的攻防速血、进化点将隐藏为 <b>❓</b>，但你可以看到自己！</div>
            </div>
        </div>

        <div id="lobby">
            <div style="background: rgba(28, 28, 35, 0.6); padding: 25px; border-radius: 16px;">
                <h3 style="margin-top:0; color:#bb86fc;">进入暗夜猎场</h3>
                <input type="text" id="p_name" placeholder="你的代号 (如: 影刃)">
                <div class="random-role-box">
                    <div class="title">🎲 随机身份</div>
                    <div class="desc">进入暗夜后，命运将随机为你分配一个身份</div>
                </div>
                <input type="text" id="room_id" placeholder="暗夜房间号 (统一输入相同号码)">
                <button class="btn-primary" onclick="joinRoom()">潜入暗夜</button>
            </div>
        </div>

        <div id="game">
            <button id="btn_leave" onclick="leaveRoom()">🚪 离开房间</button>
            <div id="status">连接中...</div>
            <div id="game-area">
                <div id="round-table-bg">暗 夜 圆 桌</div>
                <div id="player-cards"></div>
            </div>
            
            <div id="logs">等待暗夜降临...</div>
            
            <div id="actions">
                <div class="action-buttons">
                    <button onclick="submitAction('attack')" id="btn_attack" class="btn-action btn-attack">🗡️ 猎杀</button>
                    <button onclick="submitAction('defend')" id="btn_defend" class="btn-action btn-defend">🛡️ 防御</button>
                    <button onclick="submitAction('evolve')" id="btn_evolve" class="btn-action btn-evolve">🧬 进化</button>
                    <button onclick="submitAction('rest')" id="btn_rest" class="btn-action btn-rest">💤 休养</button>
                    <button onclick="submitAction('ult')" id="btn_ult" class="btn-action btn-ult">🔥 绝杀 (6点)</button>
                </div>
                <div id="targets_box">
                    <p style="margin: 0 0 10px 0; color:#ff6b6b;">🩸 选择你的目标:</p>
                    <div id="target_btns"></div>
                </div>
            </div>
            
            <div id="restart_container">
                <button onclick="restartGame()" class="btn-restart">🌑 开启下一局</button>
            </div>
        </div>
    </div>
        
        <script>
            function createStars() {
                let stars = document.getElementById('stars');
                let shadow = '';
                for (let i = 0; i < 200; i++) {
                    const x = Math.random() * window.innerWidth;
                    const y = Math.random() * window.innerHeight;
                    const size = Math.random() * 2 + 1;
                    shadow += (i ? ',' : '') + `${x}px ${y}px ${size}px rgba(255,255,255,${Math.random() * 0.8 + 0.2})`;
                }
                stars.style.boxShadow = shadow;
            }
            window.addEventListener('load', () => { createStars(); autoRejoin(); });
            window.addEventListener('resize', createStars);

            const SESSION_KEY = 'darkEvolutionSession';
            let ws = null;
            let myName = "", myRole = "random", roomId = "";
            let reconnectTimer = null;
            let leftRoom = false;
            let pendingActionType = null;

            function showGameView() {
                document.getElementById("lobby").style.display = "none";
                document.getElementById("game").style.display = "block";
            }

            function joinRoom() {
                const name = document.getElementById("p_name").value.trim();
                const room = document.getElementById("room_id").value.trim();
                if (!name || !room) return alert("代号和暗夜房间不能为空！");

                myName = name; roomId = room; myRole = "random";
                sessionStorage.setItem(SESSION_KEY, JSON.stringify({ name, room }));
                showGameView();
                connectWebsocket();
            }

            function autoRejoin() {
                const raw = sessionStorage.getItem(SESSION_KEY);
                if (!raw) return;
                let s = null;
                try { s = JSON.parse(raw); } catch (e) { s = null; }
                if (!s || !s.name || !s.room) { sessionStorage.removeItem(SESSION_KEY); return; }

                myName = s.name; roomId = s.room; myRole = "random";
                document.getElementById("p_name").value = s.name;
                document.getElementById("room_id").value = s.room;
                showGameView();
                document.getElementById("status").innerText = "🔄 正在重返暗夜...";
                connectWebsocket();
            }

            function leaveRoom() {
                leftRoom = true;
                sessionStorage.removeItem(SESSION_KEY);
                if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
                if (ws) {
                    ws.onclose = null; ws.onmessage = null;
                    try { ws.close(); } catch (e) {}
                    ws = null;
                }
                document.getElementById("lobby").style.display = "block";
                document.getElementById("game").style.display = "none";
                document.getElementById("player-cards").innerHTML = "";
                document.getElementById("logs").innerHTML = "等待暗夜降临...";
                document.getElementById("actions").style.display = "none";
                document.getElementById("targets_box").style.display = "none";
                document.getElementById("restart_container").style.display = "none";
                document.getElementById("status").innerText = "连接中...";
            }

            function triggerDeathPopup(playerName) {
                const toast = document.createElement('div');
                toast.className = 'death-toast';
                toast.innerHTML = `☠️ ${playerName} 已被暗夜吞噬！ ☠️`;
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 2000);
            }

            function triggerRevivePopup(playerName) {
                const toast = document.createElement('div');
                toast.className = 'revive-toast';
                toast.innerHTML = `🕯️ ${playerName} 从暗夜中被唤回！ 🕯️`;
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 2400);
            }

            function connectWebsocket() {
                if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
                if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) return;

                leftRoom = false;
                const proto = window.location.protocol === "https:" ? "wss" : "ws";
                const url = `${proto}://${window.location.host}/ws/` +
                            `${encodeURIComponent(roomId)}/` +
                            `${encodeURIComponent(myName)}/random`;
                ws = new WebSocket(url);

                ws.onmessage = (event) => {
                    let data;
                    try { data = JSON.parse(event.data); } catch (e) { return; }

                    if (data.type === "status") {
                        enableButtons(true);
                        document.getElementById("restart_container").style.display = "none";
                        updateBoard(data.players, data.turn);

                        const me = data.players.find(p => p.name === myName);
                        const aliveCount = data.players.filter(p => p.alive).length;

                        if (me && !me.alive) {
                            document.getElementById("actions").style.display = "none";
                            document.getElementById("status").innerText = "💀 你已被暗夜吞噬，等待本局结束...";
                        } else if (aliveCount >= 2) {
                            document.getElementById("actions").style.display = "block";
                            document.getElementById("status").innerText = "🌙 暗夜猎手集结完毕！请决定你的行动！";
                        } else {
                            document.getElementById("actions").style.display = "none";
                            document.getElementById("status").innerText = "⏳ 召集暗夜猎手... (已加入 " + aliveCount + " / 至少需要 2 人)";
                        }
                    }
                    else if (data.type === "log") {
                        addLogs(data.logs, data.turn);
                        document.getElementById("actions").style.display = "none";
                        document.getElementById("targets_box").style.display = "none";

                        const players = data.players || [];
                        const me = players.find(p => p.name === myName);
                        if (me && !me.alive) {
                            document.getElementById("status").innerText = "💀 你已被暗夜吞噬...";
                        } else {
                            document.getElementById("status").innerText = "⏳ 结算中...";
                        }

                        for (let line of data.logs) {
                            if (line.trim().startsWith("💀")) {
                                let nameMatch = line.match(/💀\\s*(.*?)\\s*被暗夜彻底吞噬/);
                                if (nameMatch && nameMatch[1]) triggerDeathPopup(nameMatch[1]);
                            }
                            if (line.includes("🕯️") && line.includes("被唤回")) {
                                let nameMatch = line.match(/🕯️[^，]*?(\\S+?)\\s*被唤回/);
                                if (nameMatch && nameMatch[1]) triggerRevivePopup(nameMatch[1]);
                            }
                        }
                    }
                    else if (data.type === "join_error") {
                        alert(data.msg);
                        leaveRoom();
                    }
                    else if (data.type === "error") {
                        alert(data.msg);
                        enableButtons(true);
                    }
                    else if (data.type === "waiting") {
                        document.getElementById("actions").style.display = "none";
                        document.getElementById("status").innerText = "⏳ 等待其他暗夜猎手行动...";
                    }
                    else if (data.type === "gameover") {
                        document.getElementById("status").innerText = data.msg;
                        document.getElementById("actions").style.display = "none";
                        document.getElementById("restart_container").style.display = "block";
                    }
                    else if (data.type === "attack_targets") {
                        let btns = document.getElementById("target_btns");
                        btns.innerHTML = "";
                        for (let t of data.targets) {
                            let btn = document.createElement("button");
                            btn.innerText = t.name;
                            btn.className = "target-btn";
                            btn.onclick = function() {
                                ws.send(JSON.stringify({type: pendingActionType, target: t.name}));
                                document.getElementById("targets_box").style.display = "none";
                                document.getElementById("actions").style.display = "none";
                                document.getElementById("status").innerText = "✅ 已提交行动，等待结算...";
                                enableButtons(false);
                            };
                            btns.appendChild(btn);
                        }
                    }
                };

                ws.onclose = function() {
                    if (leftRoom) return;
                    document.getElementById("status").innerText = "⚠️ 中断连接，尝试重连...";
                    reconnectTimer = setTimeout(connectWebsocket, 2000);
                };
                ws.onerror = function() {};
            }

            function enableButtons(isEnabled) {
                ["btn_attack","btn_defend","btn_evolve","btn_rest", "btn_ult"].forEach(id => document.getElementById(id).disabled = !isEnabled);
            }

            function updateBoard(players, current_turn) {
                let container = document.getElementById("player-cards");
                container.innerHTML = "";
                for(let p of players) {
                    let isHidden = current_turn > 1 && p.alive && p.name !== myName;

                    let atkDisplay = isHidden ? "❓" : p.atk;
                    let defDisplay = isHidden ? "❓" : p.def;
                    let spdDisplay = isHidden ? "❓" : p.spd;
                    let hpDisplay  = isHidden ? "❓" : p.hp;
                    let evoDisplay = isHidden ? "❓" : p.evo;

                    if (!p.alive) {
                        atkDisplay = "💀"; defDisplay = "💀"; spdDisplay = "💀";
                        hpDisplay = "💀"; evoDisplay = "💀";
                    }

                    if (p.name === myName && p.alive) {
                        let ultBtn = document.getElementById("btn_ult");
                        if (ultBtn) {
                            if (p.evo >= 6) {
                                ultBtn.disabled = false;
                                ultBtn.innerText = "🔥 绝杀 (6点)";
                            } else {
                                ultBtn.disabled = true;
                                ultBtn.innerText = `🔥 绝杀 (缺${6 - p.evo}点)`;
                            }
                        }
                    }

                    let cardClass = p.alive ? "player-card" : "player-card card-dead";
                    let isMeLabel = p.name === myName ? ' (你)' : '';
                    let html = `
                        <div class="${cardClass}" data-name="${p.name}">
                            <div class="card-header">
                                <div class="card-name">${p.name}${isMeLabel}</div>
                                <div class="card-role">${p.role}</div>
                            </div>
                            <div class="card-stats">
                                <div class="stat-item"><span class="stat-label">攻击</span><span class="stat-val atk">${atkDisplay}</span></div>
                                <div class="stat-item"><span class="stat-label">防御</span><span class="stat-val def">${defDisplay}</span></div>
                                <div class="stat-item"><span class="stat-label">速度</span><span class="stat-val spd">${spdDisplay}</span></div>
                                <div class="stat-item"><span class="stat-label">生命值</span><span class="stat-val hp">${hpDisplay}</span></div>
                                <div class="stat-item" style="grid-column: span 2; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 6px; margin-top: 4px;">
                                    <span class="stat-label">进化点</span>
                                    <span class="stat-val evo">${evoDisplay}</span>
                                </div>
                            </div>
                        </div>
                    `;
                    container.innerHTML += html;
                }
                requestAnimationFrame(() => arrangeSeats());
            }

            function arrangeSeats() {
                const container = document.getElementById("game-area");
                const cards = document.querySelectorAll(".player-card");
                const total = cards.length;
                if (total === 0) return;

                const rect = container.getBoundingClientRect();
                const centerX = rect.width / 2;
                const centerY = rect.height / 2;
                
                const radiusX = Math.min(rect.width * 0.36, 360);
                const radiusY = Math.min(rect.height * 0.36, 160);

                cards.forEach((card, index) => {
                    const angle = (index / total) * 2 * Math.PI - Math.PI / 2;
                    const x = centerX + radiusX * Math.cos(angle);
                    const y = centerY + radiusY * Math.sin(angle);
                    
                    card.style.position = "absolute";
                    card.style.left = x + "px";
                    card.style.top = y + "px";
                    
                    card.style.zIndex = 2 + Math.floor((Math.sin(angle) + 1) * 10);
                });
            }
            
            window.addEventListener('resize', () => {
                if(document.getElementById("game").style.display !== "none"){
                    requestAnimationFrame(() => arrangeSeats());
                }
            });

            function addLogs(logs, turn) {
                let div = document.getElementById("logs");
                div.innerHTML += `<span style="color:#bb86fc;">[暗夜进化 第 ${turn} 回合结束]</span><br>`;
                for(let l of logs) {
                    if (l.indexOf("🌙 暗夜能量") === 0 || l.indexOf("🌑 暗夜事件") === 0 || l.indexOf("🕯️") === 0) {
                        div.innerHTML += `<span style="color:#ffd700; font-weight:bold;">${l}</span><br>`;
                    } else {
                        div.innerHTML += `${l}<br>`;
                    }
                }
                div.scrollTop = div.scrollHeight;
            }

            function submitAction(type) {
                if (type === "ult") {
                    let myCard = document.querySelector(`.player-card[data-name="${myName}"]`);
                    if (myCard) {
                        let evoText = myCard.querySelector('.stat-val.evo').innerText;
                        let myEvo = parseInt(evoText);
                        if (isNaN(myEvo) || myEvo < 6) {
                            alert("⚠️ 你的进化点不足 6 点，无法发动暗夜绝杀！");
                            return; 
                        }
                    }
                }

                enableButtons(false);
                if(type === "attack" || type === "ult") {
                    pendingActionType = type;
                    document.getElementById("targets_box").style.display = "block";
                    ws.send(JSON.stringify({type: "get_attack_targets"}));
                } else {
                    ws.send(JSON.stringify({type: type}));
                    document.getElementById("actions").style.display = "none";
                    document.getElementById("status").innerText = "✅ 已提交行动，等待其他猎手...";
                }
            }

            function restartGame() {
                document.getElementById("restart_container").style.display = "none";
                ws.send(JSON.stringify({type: "restart"}));
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.websocket("/ws/{room_id}/{player_name}/{selected_role}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_name: str, selected_role: str):
    try:
        await websocket.accept()
    except Exception:
        return

    if room_id not in room_games:
        room_games[room_id] = DarkEvolutionGame()
        room_connections[room_id] = []

    room_connections[room_id].append(websocket)
    game = room_games[room_id]

    existing_player = next((p for p in game.players if p['name'] == player_name), None)

    if not existing_player:
        if len(game.players) >= MAX_PLAYERS:
            await websocket.send_json({"type": "join_error", "msg": "暗夜猎场已满（最多 6 人），请稍后再来。"})
            try:
                await websocket.close()
            except Exception:
                pass
            return

        assigned_role = pick_random_role(game.players)
        new_p = create_player(player_name, assigned_role)
        game.players.append(new_p)

    for conn in room_connections[room_id]:
        try:
            await conn.send_json({"type": "status", "players": game.players, "turn": game.turn})
        except:
            pass

    try:
        while True:
            data = await websocket.receive_json()
            action_type = data.get('type')

            if action_type == 'restart':
                room_games[room_id] = DarkEvolutionGame()
                new_game = room_games[room_id]
                old_players_data = [(p['name'], p['role']) for p in game.players]
                new_game.reset(old_players_data)

                for conn in room_connections[room_id]:
                    try:
                        await conn.send_json({"type": "status", "players": new_game.players, "turn": new_game.turn})
                    except:
                        pass
                continue

            if action_type == 'get_attack_targets':
                targets = [p for p in game.get_alive_players() if p['name'] != player_name]
                if game.actions_this_round.get(player_name):
                    await websocket.send_json({"type": "error", "msg": "你已出手，不能再次猎杀"})
                else:
                    await websocket.send_json({"type": "attack_targets", "targets": targets})
                continue

            success, msg = game.submit_action(player_name, data)
            if not success:
                await websocket.send_json({"type": "error", "msg": msg})
                continue

            is_round_done, result = game.check_and_execute_round()

            if is_round_done:
                logs = result
                turn = game.turn - 1

                for conn in room_connections[room_id]:
                    try:
                        await conn.send_json({"type": "log", "logs": logs, "turn": turn})
                        await conn.send_json({"type": "status", "players": game.players, "turn": game.turn})
                    except:
                        pass

                if len(game.get_alive_players()) <= 1:
                    winner = game.get_alive_players()[0] if game.get_alive_players() else None
                    for conn in room_connections[room_id]:
                        try:
                            await conn.send_json({"type": "gameover", "msg": f"🏆 暗夜之主诞生！ {winner['name'] if winner else '无人生还！'} 胜出！"})
                        except:
                            pass
                    continue

            else:
                await websocket.send_json({"type": "waiting"})

    except WebSocketDisconnect:
        if room_id in room_connections and websocket in room_connections[room_id]:
            room_connections[room_id].remove(websocket)
        
        if room_id in room_games:
            game = room_games[room_id]
            old_len = len(game.players)
            game.players = [p for p in game.players if p['name'] != player_name]
            
            if len(game.players) < old_len:
                if player_name in game.actions_this_round:
                    del game.actions_this_round[player_name]

                if len(game.players) == 0:
                    del room_games[room_id]
                    del room_connections[room_id]
                else:
                    for conn in room_connections.get(room_id, []):
                        try:
                            await conn.send_json({"type": "status", "players": game.players, "turn": game.turn})
                        except:
                            pass
    except Exception as e:
        if room_id in room_connections and websocket in room_connections[room_id]:
            room_connections[room_id].remove(websocket)
            
        if room_id in room_games:
            game = room_games[room_id]
            old_len = len(game.players)
            game.players = [p for p in game.players if p['name'] != player_name]
            if len(game.players) < old_len:
                if player_name in game.actions_this_round:
                    del game.actions_this_round[player_name]
                if len(game.players) == 0:
                    del room_games[room_id]
                    del room_connections[room_id]
                else:
                    for conn in room_connections.get(room_id, []):
                        try:
                            await conn.send_json({"type": "status", "players": game.players, "turn": game.turn})
                        except:
                            pass

# ===== 适配 Render 的端口分配 =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)