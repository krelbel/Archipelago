from __future__ import annotations
import os
import sys
import asyncio
import shutil
import time

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
# - Buzz when you receive various items!

from buttplug import Client, WebsocketConnector, ProtocolSpec

async def haltbuzz(ctx: BPIOContext):
    for dev in ctx.client.devices.values():
        for actuator in dev.actuators:
            await actuator.command(0)
        for rotatory_actuator in dev.rotatory_actuators:
            await rotatory_actuator.command(0, True)

async def buzz(ctx: BPIOContext, duration: float = 0.5, halt_when_finished: bool = True):
    for dev in ctx.client.devices.values():
        for linear_actuator in dev.linear_actuators:
            linear_actuator(duration * 1000, 0.5)

    for dev in ctx.client.devices.values():
        for actuator in dev.actuators:
            await actuator.command(ctx.strength)
        for rotatory_actuator in dev.rotatory_actuators:
            await rotatory_actuator.command(ctx.strength, True)

    await asyncio.sleep(duration)

    # Only turn vibrations off if we know this isn't part of a sequence of
    # different intensity vibrations, to avoid stuttering
    if halt_when_finished == False:
        return

    await haltbuzz(ctx)

async def bpconnect(ctx: BPIOContext, ccp: BPIOClientCommandProcessor):
    try:
        await ctx.client.connect(ctx.connector)
    except Exception as e:
        logger.error(f"Err1, ex: {e}")

    await ctx.client.start_scanning()
    await asyncio.sleep(5)
    await ctx.client.stop_scanning()

    if len(ctx.client.devices) == 0:
        ccp.output(f"No devices connected")
    else:
        for idx, dev in ctx.client.devices.items():
            ccp.output(f"Connected device {idx}: {dev}")

async def bptest(ctx: BPIOContext):
    await buzz(ctx, 0.1)
    await asyncio.sleep(0.1)
    await buzz(ctx, 0.1)
    await asyncio.sleep(0.1)
    await buzz(ctx, 0.5)

async def bp_trap(ctx: BPIOContext):
    await buzz(ctx, 4.0)

async def bp_progression(ctx: BPIOContext):
    await buzz(ctx, 3.0)

async def bp_useful(ctx: BPIOContext):
    await buzz(ctx, 2.0)

async def bp_trash(ctx: BPIOContext):
    await buzz(ctx, 1.0)

async def bp_location(ctx: BPIOContext):
    await buzz(ctx, 0.5)

async def bp_string(ctx: BPIOContext, mcmd: String):
    for subcmd in mcmd.split(' '):
        splitcmd = subcmd.split(',')
        strength = splitcmd[0]
        duration = splitcmd[1]
        if float(strength) == 0.0:
            await asyncio.sleep(float(duration))
        else:
            ctx.strength = float(strength)
            await buzz(ctx, float(duration), False)

    await haltbuzz(ctx)

# Demonstrate a less trivial vibration pattern using "strength,duration" formatted strings
async def bp_multistr(ctx: BPIOContext):
    await bp_string(ctx, "0.1,0.2 0.2,0.2 0.3,0.2 0.4,0.2 0.5,0.2 0.6,0.2 0.7,0.2 0.8,0.2 0.9,0.2 1.0,0.2")
    await asyncio.sleep(0.5)
    await bp_string(ctx, "0.1,0.1 0.2,0.1 0.3,0.1 0.4,0.1 0.5,0.1 0.6,0.1 0.7,0.1 0.8,0.1 0.9,0.1 1.0,0.2")
    await asyncio.sleep(0.5)
    await bp_string(ctx, "0.1,0.1 0.2,0.1 0.3,0.1 0.4,0.1 0.5,0.1 0.6,0.1 0.7,0.1 0.8,0.1 0.9,0.1 1.0,0.2")
    await asyncio.sleep(0.5)
    await bp_string(ctx, "0.1,0.1 0.2,0.1 0.3,0.1 0.4,0.1 0.5,0.1 0.6,0.1 0.7,0.1 0.8,0.1 0.9,0.1 1.0,0.2")

async def bp_deathlink(ctx: BPIOContext):
    await bp_multistr(ctx)

class BPIOClientCommandProcessor(ClientCommandProcessor):
    ctx: BPIOContext

    def _cmd_bp(self):
        """Connect to an Intiface Central server device"""
        self.output(f"Connecting BP")
        try:
            asyncio.create_task(bpconnect(self.ctx, self))
        except Exception as e:
            logger.error(f"Err, ex: {e}")
            return

    def _cmd_bpstrength(self, strength: float = 0.5):
        """Set vibration strength"""
        self.output(f"Setting vibration strength to {strength}")
        self.ctx.strength = float(strength)

    def _cmd_bpdc(self):
        """Disconnect from an Intiface Central server device"""
        self.output(f"Disconnecting BP")
        asyncio.create_task(self.ctx.client.disconnect())

    def _cmd_bptest(self):
        """Test BP"""
        self.output(f"Testing BP")
        asyncio.create_task(bp_multistr(self.ctx))

if __name__ == '__main__':

    class BPIOContext(CommonContext):
        command_processor: int = BPIOClientCommandProcessor
        tags = {"AP", "TextOnly"}
        game = ""  # empty matches any game since 0.3.2
        items_handling = 0b111  # receive all items for /received
        want_slot_data = False  # Can't use game specific slot_data

        client = Client("BPIO Client", ProtocolSpec.v3)
        connector = WebsocketConnector("ws://127.0.0.1:12345", logger=client.logger)
        strength = 0.5

        async def server_auth(self, password_requested: bool = False):
            if password_requested and not self.password:
                await super(TextContext, self).server_auth(password_requested)
            await self.get_username()
            await self.send_connect()

        def on_package(self, cmd: str, args: dict):
            if cmd == "Connected":
                self.game = self.slot_info[self.slot].game

            elif cmd == 'ReceivedItems':
                start_index = args["index"]

                if start_index == len(self.items_received):
                    for item in args["items"]:
                        if item.flags & 0b001:  # progression item
                            #logger.info(f"Prog")
                            asyncio.create_task(bp_progression(self))
                        elif item.flags & 0b010:  # useful item
                            #logger.info(f"Useful")
                            asyncio.create_task(bp_useful(self))
                        elif item.flags & 0b100:  # trap item
                            #logger.info(f"Trap")
                            asyncio.create_task(bp_trap(self))
                        else:  # trash item
                            #logger.info(f"Trash")
                            asyncio.create_task(bp_trash(self))

            # These may clobber your own item buzzing; implement a queue system?
            elif cmd == "RoomUpdate":
                if "checked_locations" in args:
                    checked = set(args["checked_locations"])
                    for location in checked:
                        logger.info(f"Location")
                        asyncio.create_task(bp_location(self))

            elif cmd == "Bounced":
                tags = args.get("tags", [])
                # we can skip checking "DeathLink" in ctx.tags, as otherwise we wouldn't have been send this
                if "DeathLink" in tags and self.last_death_link != args["data"]["time"]:
                    asyncio.create_task(bp_deathlink(self))

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

