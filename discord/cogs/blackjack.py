import asyncio
import os
import random
from typing import List, Tuple, Union

import discord
from discord.ext import commands
from modules.card import Card
from modules.economy import Economy
from modules.helpers import *
from PIL import Image


class Blackjack(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.economy = Economy()
    
    def check_bet(
        self,
        ctx: commands.Context,
        bet: int = DEFAULT_BET,
    ):
        bet = int(bet)
        if bet <= 0:
            raise commands.errors.BadArgument()
        current = self.economy.get_entry(ctx.author.id)[1]
        if bet > current:
            raise InsufficientFundsException(current, bet)

    @staticmethod
    def hand_to_images(hand: List[Card]) -> List[Image.Image]:
        return [
            Image.open(os.path.join(ABS_PATH, 'modules/cards/', card.image))
            for card in hand
        ]

    @staticmethod
    def center(*hands: Tuple[Image.Image]) -> Image.Image:
        """Tạo bàn blackjack và đặt các lá bài"""
        bg: Image.Image = Image.open(
            os.path.join(ABS_PATH, 'modules/', 'table.png')
        )
        bg_center_x = bg.size[0] // 2
        bg_center_y = bg.size[1] // 2

        img_w = hands[0][0].size[0]
        img_h = hands[0][0].size[1]

        start_y = bg_center_y - (((len(hands) * img_h) +
            ((len(hands) - 1) * 15)) // 2)

        for hand in hands:
            start_x = bg_center_x - (((len(hand) * img_w) +
                ((len(hand) - 1) * 10)) // 2)
            for card in hand:
                bg.alpha_composite(card, (start_x, start_y))
                start_x += img_w + 10
            start_y += img_h + 15

        return bg

    def output(self, name, *hands: Tuple[List[Card]]) -> None:
        self.center(*map(self.hand_to_images, hands)).save(f'{name}.png')

    @staticmethod
    def calc_hand(hand: List[List[Card]]) -> int:
        """Tính tổng điểm bài (xử lý quân Át)"""
        non_aces = [c for c in hand if c.symbol != 'A']
        aces = [c for c in hand if c.symbol == 'A']
        total = 0

        for card in non_aces:
            if not card.down:
                if card.symbol in 'JQK':
                    total += 10
                else:
                    total += card.value

        for card in aces:
            if not card.down:
                if total <= 10:
                    total += 11
                else:
                    total += 1

        return total

    @commands.command(
        aliases=['bj'],
        brief="Chơi Blackjack.\nTiền cược phải lớn hơn $0",
        usage=f"blackjack [tiền cược - mặc định=${DEFAULT_BET}]"
    )
    async def blackjack(self, ctx: commands.Context, bet: int = DEFAULT_BET):
        self.check_bet(ctx, bet)

        deck = [Card(suit, num) for num in range(2, 15) for suit in Card.suits]
        random.shuffle(deck)

        player_hand: List[Card] = []
        dealer_hand: List[Card] = []

        player_hand.append(deck.pop())
        dealer_hand.append(deck.pop())
        player_hand.append(deck.pop())
        dealer_hand.append(deck.pop().flip())

        async def out_table(**kwargs) -> discord.Message:
            """Gửi ảnh bàn chơi hiện tại"""
            self.output(ctx.author.id, dealer_hand, player_hand)
            embed = make_embed(**kwargs)
            file = discord.File(
                f"{ctx.author.id}.png", filename=f"{ctx.author.id}.png"
            )
            embed.set_image(url=f"attachment://{ctx.author.id}.png")
            msg = await ctx.send(file=file, embed=embed)
            return msg
        
        def check(reaction: discord.Reaction, user: Union[discord.Member, discord.User]) -> bool:
            return all((
                str(reaction.emoji) in ("🇸", "🇭"),
                user == ctx.author,
                user != self.client.user,
                reaction.message == msg
            ))

        standing = False

        while True:
            player_score = self.calc_hand(player_hand)
            dealer_score = self.calc_hand(dealer_hand)

            if player_score == 21:
                bet = int(bet * 1.5)
                self.economy.add_money(ctx.author.id, bet)
                result = ("Blackjack! 🎉", 'won')
                break
            elif player_score > 21:
                self.economy.add_money(ctx.author.id, bet * -1)
                result = ("Bạn bị quắc 😵", 'lost')
                break

            msg = await out_table(
                title="Lượt của bạn",
                description=(
                    f"**Bài của bạn:** {player_score}\n"
                    f"**Bài nhà cái:** {dealer_score}"
                )
            )

            await msg.add_reaction("🇭")  # Rút bài
            await msg.add_reaction("🇸")  # Dừng

            try:
                reaction, _ = await self.client.wait_for(
                    'reaction_add', timeout=60, check=check
                )
            except asyncio.TimeoutError:
                await msg.delete()
                return

            if str(reaction.emoji) == "🇭":
                player_hand.append(deck.pop())
                await msg.delete()
                continue
            elif str(reaction.emoji) == "🇸":
                standing = True
                break

        if standing:
            dealer_hand[1].flip()
            player_score = self.calc_hand(player_hand)
            dealer_score = self.calc_hand(dealer_hand)

            while dealer_score < 17:
                dealer_hand.append(deck.pop())
                dealer_score = self.calc_hand(dealer_hand)

            if dealer_score == 21:
                self.economy.add_money(ctx.author.id, bet * -1)
                result = ('Nhà cái Blackjack', 'lost')
            elif dealer_score > 21:
                self.economy.add_money(ctx.author.id, bet)
                result = ("Nhà cái bị quắc", 'won')
            elif dealer_score == player_score:
                result = ("Hòa 🤝", 'kept')
            elif dealer_score > player_score:
                self.economy.add_money(ctx.author.id, bet * -1)
                result = ("Bạn thua 😭", 'lost')
            else:
                self.economy.add_money(ctx.author.id, bet)
                result = ("Bạn thắng 🎉", 'won')

        color = (
            discord.Color.red() if result[1] == 'lost'
            else discord.Color.green() if result[1] == 'won'
            else discord.Color.blue()
        )

        try:
            await msg.delete()
        except:
            pass

        msg = await out_table(
            title=result[0],
            color=color,
            description=(
                f"**Kết quả: {result[1].upper()} ${bet}**\n"
                f"Bài của bạn: {player_score}\n"
                f"Bài nhà cái: {dealer_score}"
            )
        )

        os.remove(f'./{ctx.author.id}.png')


def setup(client: commands.Bot):
    client.add_cog(Blackjack(client))
