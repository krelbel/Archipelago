from __future__ import annotations
import os
import sys
import asyncio
import shutil
import time
import typing
from enum import IntEnum

import ModuleUpdate

ModuleUpdate.update()

import Utils

if __name__ == "__main__":
    Utils.init_logging("BPIOClient", exception_logger="Client")

from NetUtils import NetworkItem, ClientStatus
from CommonClient import gui_enabled, logger, get_base_parser, ClientCommandProcessor, \
    CommonContext, server_loop

# Instructions:
# - Install and run https://intiface.com/central/
# - Start Intiface Central server, click devices, start scanning, hold power
#   button for 3 seconds to pair device with intiface
# - Clone https://github.com/Siege-Wizard/buttplug-py/tree/main/buttplug into
#   your AP directory (which should contain BPIOClient.py and a subfolder named
#   buttplug alongside the rest of the AP clone)
# - Run BPIOClient.py, connect to your game's room and slot
# - Run /bp, verify you've connected, run /bptest to test, /bpdc to disconnect
# - Run /bpstrength to adjust the strength from 0.0 to 1.0 (default 0.5)
# - Buzz when you send and receive various items!

from buttplug import Client, WebsocketConnector, ProtocolSpec


class PatternType(IntEnum):
    onitem = 1  # buzzes when you get an item, off otherwise
    percent = 2  # strength increases based on the % of your locations you have checked
    time = 3  # strength increases the longer you go without sending a check


async def haltbuzz(ctx: BPIOContext):
    for dev in ctx.client.devices.values():
        for actuator in dev.actuators:
            await actuator.command(0)
        for rotatory_actuator in dev.rotatory_actuators:
            await rotatory_actuator.command(0, True)
    await asyncio.sleep(0.1)


async def buzz(ctx: BPIOContext, duration: float = 0.5, singlebuzz: bool = True):
    if singlebuzz:
        await ctx.bplock.acquire()
    elif not ctx.bplock.locked():
        logger.error("Error: sequential buzzes called without locking")

    if ctx.bpenable:
        for dev in ctx.client.devices.values():
            for linear_actuator in dev.linear_actuators:

                # Flip Duration
                if duration <= 0:
                    logger.error("Error: Duration can't be equal or less than 0")
                duration = 3 / duration
                # if at bottom or going down send to top
                if ctx.bplinpos == 0:
                    ctx.bplinpos = 1
                    await linear_actuator.command(int(duration * 1000), 1)
                # otherwise send to bottom
                else:
                    ctx.bplinpos = 0
                    await linear_actuator.command(int(duration * 1000), 0)

        for dev in ctx.client.devices.values():
            for actuator in dev.actuators:
                await actuator.command(ctx.strength)
            for rotatory_actuator in dev.rotatory_actuators:
                await rotatory_actuator.command(ctx.strength, True)

        await asyncio.sleep(duration)

    # Only turn vibrations off if we know this isn't part of a sequence of
    # different intensity vibrations, to avoid stuttering
    if not singlebuzz:
        return

    await haltbuzz(ctx)
    ctx.bplock.release()


async def bpconnect(ctx: BPIOContext, ccp: BPIOClientCommandProcessor):
    try:
        await ctx.client.connect(ctx.connector)
    except Exception as e:
        logger.error(f"Error connecting: {e}")

    await ctx.client.start_scanning()
    await asyncio.sleep(5)
    await ctx.client.stop_scanning()

    if len(ctx.client.devices) == 0:
        ccp.output(f"No devices connected")
    else:
        for idx, dev in ctx.client.devices.items():
            ccp.output(f"Connected device {idx}: {dev}")
            ctx.bpenable = True
        await buzz(ctx, 0.5)


async def bp_trap(ctx: BPIOContext):
    print("starting trap")
    await bp_string(ctx, "0.1,1.0 0.1,1.0 0.2,1.0 0.3,1.0 0.4,1.0 0.5,1.0 0.6,1.0 0.7,1.0 0.8,1.0 0.9,1.0 1.0,1.0")


async def bp_progression(ctx: BPIOContext):
    print("starting prog")
    # await bp_string(ctx, "1.0,1.0 0.2,0.1 0.1,0.1 1.0,1.0")
    # just the above on repeat for 9.6 seconds, close enough to 10 seconds
    await bp_string(ctx, "1.0,1.0 0.2,0.1 0.1,0.1 1.0,1.0 0.2,0.1 0.1,0.1 1.0,1.0 0.2,0.1 0.1,0.1 1.0,1.0 0.2,0.1 0.1,0.1 1.0,1.0 0.2,0.1 0.1,0.1 1.0,1.0 0.2,0.1 0.1,0.1 1.0,1.0 0.2,0.1 0.1,0.1 1.0,1.0 0.2,0.1 0.1,0.1 1.0,1.0")


async def bp_useful(ctx: BPIOContext):
    print("starting useful")
    await bp_string(ctx, "1.0,1.0 0.2,1.0 0.1,1.0 1.0,1.0 0.2,1.0 0.1,1.0 1.0,1.0 0.2,1.0 0.1,1.0 1.0,1.0 0.1,1.0")


async def bp_trash(ctx: BPIOContext):
    print("starting trash")
    await bp_string(ctx, "1.0,1.0 1.0,1.0 0.9,1.0 0.8,1.0 0.7,1.0 0.6,1.0 0.5,1.0 0.4,1.0 0.3,1.0 0.2,1.0 0.1,1.0")


async def bp_location(ctx: BPIOContext):
    print("starting location")
    if ctx.pattern == PatternType.onitem:
        await bp_string(ctx, "1.0,0.5")

stop_buzz = False
loop_once = False
change_buzz = False


async def bp_string(ctx: BPIOContext, mcmd: String):
    async with ctx.bplock:
        global stop_buzz
        global change_buzz
        stop_buzz = False
        if ctx.pattern == PatternType.onitem:
            # if you have onitem pattern, it should only loop the pattern one time
            global loop_once
            loop_once = True
        while not stop_buzz:
            for subcmd in mcmd.split(' '):
                splitcmd = subcmd.split(',')
                strength = splitcmd[0]
                duration = splitcmd[1]
                if float(strength) == 0.0:
                    await asyncio.sleep(float(duration))
                else:
                    ctx.strength = float(strength) * ctx.base_strength
                    if ctx.strength > 1:
                        ctx.strength = 1
                    await buzz(ctx, float(duration), False)
                if stop_buzz:
                    print("stop buzzing mid loop")
                    await haltbuzz(ctx)
                    return
            if loop_once:
                await haltbuzz(ctx)
                return
            print(ctx.pattern, " current pattern")
            if ctx.pattern == PatternType.time:
                ctx.base_strength = ctx.base_strength + .05
                if change_buzz:
                    ctx.base_strength = .05
                    change_buzz = False
                print(ctx.base_strength, "base strength is that")
        await haltbuzz(ctx)


# Demonstrate a less trivial vibration pattern using "strength,duration" formatted strings
async def bp_multistr(ctx: BPIOContext):
    # await bp_string(ctx, "0.1,1.0 0.2,1.0 0.3,1.0 0.4,1.0 0.5,1.0 0.6,1.0 0.7,1.0 0.8,1.0 0.9,1.0 1.0,1.0")
    await bp_string(ctx, "0.1,1.0 0.2,1.0")


class BPIOClientCommandProcessor(ClientCommandProcessor):
    ctx: BPIOContext

    def _cmd_bp(self):
        """Connect to an Intiface Central server device"""
        self.output(f"Connecting BP")
        try:
            asyncio.create_task(bpconnect(self.ctx, self))
        except Exception as e:
            logger.error(f"Error connecting: {e}")
            return

    def _cmd_bppatt(self, pattern: PatternType):
        """Set desired pattern type.
        1: Vibrates when an item is received based on what item was received. Inactive otherwise.
        2: Vibrates constantly, where the strength of the vibration is based on the % of your checks you have sent.
        3: Vibrates constantly, with strength increasing the longer you take between checks."""
        self.output(f"Setting vibration type to {pattern}")
        global stop_buzz
        stop_buzz = True
        # self.ctx.pattern = pattern
        BPIOContext.pattern = pattern

    def _cmd_bpstrength(self, strength: float = 0.5):
        """Set vibration strength for Pattern Type 1 mode"""
        self.output(f"Setting vibration strength to {strength}")
        self.ctx.base_strength = float(strength)

    def _cmd_bpdc(self):
        """Disconnect from an Intiface Central server device"""
        self.output(f"Disconnecting BP")
        asyncio.create_task(self.ctx.client.disconnect())

    def _cmd_bptest(self):
        """Test BP"""
        self.output(f"Testing BP")
        global loop_once
        loop_once = True
        asyncio.create_task(bp_multistr(self.ctx))

    def _cmd_bpdisable(self):
        """Temporarily disable BP (for clearing a big queue of events)"""
        self.output(f"Clearing BP queue")
        global stop_buzz
        stop_buzz = True
        self.ctx.bpenable = False

    def _cmd_bpenable(self):
        """Reenable BP (for clearing a big queue of events)"""
        self.output(f"Reenabling BP queue")
        self.ctx.bpenable = True


if __name__ == '__main__':

    class BPIOContext(CommonContext):
        command_processor: int = BPIOClientCommandProcessor
        tags = {"AP", "TextOnly"}
        game = ""  # empty matches any game since 0.3.2
        items_handling = 0b111  # receive all items for /received
        want_slot_data = False  # Can't use game specific slot_data

        client = Client("BPIO Client", ProtocolSpec.v3)
        connector = WebsocketConnector("ws://192.168.1.4:12345", logger=client.logger)
        base_strength = 0.5
        strength = 0.5
        pattern = PatternType.time
        bpenable = False
        bplinpos = 1  # saved linear position 0-bottom 1-top
        checked_loc_count: int = 0
        missing_loc_count: int = 5

        async def server_auth(self, password_requested: bool = False):
            if password_requested and not self.password:
                await super(TextContext, self).server_auth(password_requested)
            await self.get_username()
            await self.send_connect()

        def on_package(self, cmd: str, args: dict):
            # Suppress all events while disabled (to clear queues after spam)
            global stop_buzz
            if not self.bpenable:
                pass

            elif cmd == 'Connected':
                BPIOContext.checked_loc_count = len(set(args["checked_locations"]))
                print(BPIOContext.checked_loc_count, "checked loc count")
                BPIOContext.missing_loc_count = len(set(args["missing_locations"]))
                print(BPIOContext.missing_loc_count, "missing loc count")
                if BPIOContext.pattern == PatternType.percent:
                    BPIOContext.base_strength = BPIOContext.checked_loc_count / (BPIOContext.checked_loc_count + BPIOContext.missing_loc_count)
                    print(BPIOContext.base_strength, "base strength")
                elif BPIOContext.pattern == PatternType.time:
                    BPIOContext.base_strength = .05
                # if the type is onitem, then base strength does not get altered by the Connected packet

            elif cmd == 'ReceivedItems':
                print("received items starting")
                stop_buzz = True
                for item in args["items"]:
                    if item.flags & 0b001:  # progression item
                        asyncio.create_task(bp_progression(self))
                    elif item.flags & 0b010:  # useful item
                        asyncio.create_task(bp_useful(self))
                    elif item.flags & 0b100:  # trap item
                        asyncio.create_task(bp_trap(self))
                    else:  # trash item
                        asyncio.create_task(bp_trash(self))

            elif cmd == "RoomUpdate":
                # if "checked_locations" in args:
                #     stop_buzz = True
                #     checked = set(args["checked_locations"])
                #     for location in checked:
                #         asyncio.create_task(bp_location(self))
                if "checked_locations" in args:
                    print("current pattern type is ", BPIOContext.pattern)
                    print("checked locations packet")
                    checked = set(args["checked_locations"])
                    BPIOContext.checked_loc_count += len(checked)
                    print(BPIOContext.checked_loc_count, "checked loc count")
                    BPIOContext.missing_loc_count -= len(checked)
                    print(BPIOContext.missing_loc_count, "missing loc count")

                    if BPIOContext.pattern == 2:
                        BPIOContext.base_strength = BPIOContext.checked_loc_count / (BPIOContext.checked_loc_count + BPIOContext.missing_loc_count)
                        print(BPIOContext.base_strength, "base strength")
                    elif BPIOContext.pattern == 3:
                        global change_buzz
                        change_buzz = True
                        BPIOContext.base_strength = .05
                        print("resetting base strength to .05")

        def run_gui(self) -> None:
            from kvui import GameManager

            class BPIOManager(GameManager):
                logging_pairs = [
                    ("Client", "Archipelago"),
                ]
                base_title = "Archipelago BPIO Client"

            self.ui = BPIOManager(self)
            self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")


    async def main(args):
        ctx = BPIOContext(args.connect, args.password)
        ctx.bplock = asyncio.Lock()
        ctx.auth = args.name
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")

        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()

        await ctx.exit_event.wait()
        await ctx.shutdown()


    import colorama

    parser = get_base_parser(description="BPIO Archipelago Client, for BPIO interfacing.")
    parser.add_argument('--name', default=None, help="Slot Name to connect as.")
    parser.add_argument("url", nargs="?", help="Archipelago connection url")
    args = parser.parse_args()

    if args.url:
        url = urllib.parse.urlparse(args.url)
        args.connect = url.netloc
        if url.username:
            args.name = urllib.parse.unquote(url.username)
        if url.password:
            args.password = urllib.parse.unquote(url.password)

    colorama.init()

    asyncio.run(main(args))
    colorama.deinit()
