
import os
import re
import random
import asyncio
from datetime import datetime

import pytz
from colorama import Fore, Style, init
from eth_account import Account
from web3 import Web3
from aiohttp import ClientSession, ClientTimeout, BasicAuth
from aiohttp_socks import ProxyConnector

init(autoreset=True)
wib = pytz.timezone('Asia/Jakarta')


class AssetoFinance:
    def __init__(self) -> None:
        self.RPC_URL = "https://atlantic.dplabs-internal.com/"
        self.EXPLORER = "https://atlantic.pharosscan.xyz/tx/"
        self.USDT_CONTRACT_ADDRESS = "0xE7E84B8B4f39C507499c40B4ac199B050e2882d5"
        self.CASH_CONTRACT_ADDRESS = "0x56f4add11d723412D27A9e9433315401B351d6E3"

        
        self.CONTRACT_ABI = [
            {"inputs": [{"internalType": "address", "name": "owner", "type": "address"},
                         {"internalType": "address", "name": "spender", "type": "address"}],
             "name": "allowance", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
             "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "address", "name": "spender", "type": "address"},
                         {"internalType": "uint256", "name": "value", "type": "uint256"}],
             "name": "approve", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
             "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"internalType": "address", "name": "account", "type": "address"}],
             "name": "balanceOf", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
             "stateMutability": "view", "type": "function"},
            
            {"inputs": [{"internalType": "address", "name": "asset", "type": "address"},
                         {"internalType": "uint256", "name": "amount", "type": "uint256"}],
             "name": "redemption", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            
            {"inputs": [{"internalType": "address", "name": "asset", "type": "address"},
                         {"internalType": "uint256", "name": "amount", "type": "uint256"}],
             "name": "subscribe", "outputs": [], "stateMutability": "nonpayable", "type": "function"}
        ]

        
        self.USDT_ABI = self.CONTRACT_ABI + [
            {"inputs": [], "name": "decimals", "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
             "stateMutability": "view", "type": "function"}
        ]

        self.proxies = []
        self.proxy_index = 0
        self.account_proxies = {}
        self.used_nonce = {}
        self.subscribed_amounts = {}
        self.tx_count = 0
        self.min_delay = 0
        self.max_delay = 0

    def clear_terminal(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def log(self, message):
        print(f"{Fore.CYAN + Style.BRIGHT}[ {datetime.now().astimezone(wib).strftime('%x %X %Z')} ]{Style.RESET_ALL} "
              f"{Fore.WHITE + Style.BRIGHT}|{Style.RESET_ALL} {message}", flush=True)

    def welcome(self):
        print(f"""
{Fore.GREEN + Style.BRIGHT}  ╔═══════════════════════════════════════════════════╗
{Fore.GREEN + Style.BRIGHT}  ║         Asseto Finance Auto BOT v15              ║
{Fore.GREEN + Style.BRIGHT}  ║                                                 ║
{Fore.GREEN + Style.BRIGHT}  ║   1. Redeem ALL CASH+ (if ≥1)                   ║
{Fore.GREEN + Style.BRIGHT}  ║   2. Random 1-9 USDT Subscribe → Redeem         ║
{Fore.GREEN + Style.BRIGHT}  ║                ║
{Fore.GREEN + Style.BRIGHT}  ╚═══════════════════════════════════════════════════╝{Style.RESET_ALL}
        """)

    async def load_proxies(self):
        if not os.path.exists("proxy.txt"):
            self.log(f"{Fore.YELLOW + Style.BRIGHT}proxy.txt not found. Running without proxy.{Style.RESET_ALL}")
            return
        with open("proxy.txt", 'r', encoding='utf-8') as f:
            self.proxies = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        self.log(f"{Fore.GREEN + Style.BRIGHT}Loaded {len(self.proxies)} proxies{Style.RESET_ALL}")

    def get_next_proxy(self, address):
        if address not in self.account_proxies:
            if not self.proxies:
                return None
            proxy = self.proxies[self.proxy_index % len(self.proxies)]
            self.account_proxies[address] = proxy
            self.proxy_index += 1
        return self.account_proxies[address]

    def build_proxy_config(self, proxy_str):
        if not proxy_str:
            return None, None, None
        if proxy_str.startswith(("socks4://", "socks5://")):
            return ProxyConnector.from_url(proxy_str), None, None
        match = re.match(r"(?:http://)?(.+):(.+)@(.+):(\d+)", proxy_str)
        if match:
            user, pwd, host, port = match.groups()
            return None, f"http://{host}:{port}", BasicAuth(user, pwd)
        return None, f"http://{proxy_str}", None

    def generate_address(self, pk: str):
        try:
            return Account.from_key(pk).address
        except:
            return None

    def mask_account(self, addr):
        return addr[:6] + "******" + addr[-4:]

    async def get_web3_with_proxy(self, address: str, use_proxy: bool):
        proxy_str = self.get_next_proxy(address) if use_proxy else None
        connector, proxy_url, auth = self.build_proxy_config(proxy_str)
        request_kwargs = {"timeout": 60}
        if use_proxy and proxy_url:
            request_kwargs["proxies"] = {"http": proxy_url, "https": proxy_url}
            if auth:
                request_kwargs["proxy_auth"] = auth

        web3 = Web3(Web3.HTTPProvider(self.RPC_URL, request_kwargs=request_kwargs))
        try:
            web3.eth.get_block_number()
            return web3
        except:
            raise Exception("RPC Connection Failed")

    async def get_token_balance(self, address: str, contract_addr: str, use_proxy: bool, is_usdt: bool = False):
        try:
            web3 = await self.get_web3_with_proxy(address, use_proxy)
            abi = self.USDT_ABI if is_usdt else self.CONTRACT_ABI
            contract = web3.eth.contract(address=web3.to_checksum_address(contract_addr), abi=abi)
            balance = contract.functions.balanceOf(address).call()
            if is_usdt:
                decimals = contract.functions.decimals().call()
            else:
                decimals = 18  
            return balance / (10 ** decimals)
        except Exception as e:
            token_name = "USDT" if is_usdt else "CASH+"
            self.log(f"{Fore.RED+Style.BRIGHT}Balance Error ({token_name}): {str(e)[:80]}{Style.RESET_ALL}")
            return None

    async def send_raw_tx(self, signed_tx, use_proxy: bool, address: str):
        payload = {"jsonrpc": "2.0", "method": "eth_sendRawTransaction", "params": [signed_tx], "id": 1}
        proxy_str = self.get_next_proxy(address) if use_proxy else None
        connector, proxy_url, auth = self.build_proxy_config(proxy_str)
        session = ClientSession(connector=connector, timeout=ClientTimeout(total=30))
        try:
            async with session.post(self.RPC_URL, json=payload, proxy=proxy_url, proxy_auth=auth) as resp:
                data = await resp.json()
                if 'result' in data:
                    return data['result']
                raise Exception(data.get('error', {}).get('message', 'Unknown'))
        finally:
            await session.close()

    async def wait_for_receipt(self, tx_hash, use_proxy: bool, address: str):
        web3 = await self.get_web3_with_proxy(address, use_proxy)
        for _ in range(100):
            try:
                receipt = web3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    return receipt
            except:
                pass
            await asyncio.sleep(3)
        raise Exception("Timeout")

    async def approve_token(self, pk: str, address: str, router: str, asset: str, amount_wei: int, use_proxy: bool):
        web3 = await self.get_web3_with_proxy(address, use_proxy)
        token = web3.eth.contract(address=asset, abi=self.CONTRACT_ABI)
        allowance = token.functions.allowance(address, router).call()
        if allowance >= amount_wei:
            return True

        try:
            approve_data = token.functions.approve(router, amount_wei)
            gas = approve_data.estimate_gas({"from": address})
            tx = approve_data.build_transaction({
                "from": address,
                "gas": int(gas * 1.3),
                "maxFeePerGas": web3.to_wei(2, "gwei"),
                "maxPriorityFeePerGas": web3.to_wei(1, "gwei"),
                "nonce": self.used_nonce[address],
                "chainId": web3.eth.chain_id,
            })
            signed = web3.eth.account.sign_transaction(tx, pk)
            tx_hash = await self.send_raw_tx(signed.raw_transaction.hex(), use_proxy, address)
            receipt = await self.wait_for_receipt(tx_hash, use_proxy, address)
            if receipt.status == 1:
                self.used_nonce[address] += 1
                self.log(f"{Fore.CYAN+Style.BRIGHT}   Approve Success | Block: {receipt.blockNumber}{Style.RESET_ALL}")
                await asyncio.sleep(5)
                return True
        except Exception as e:
            self.log(f"{Fore.RED+Style.BRIGHT}   Approve Failed: {str(e)[:80]}{Style.RESET_ALL}")
        return False

    async def perform_subscribe(self, pk: str, address: str, amount: float, use_proxy: bool):
        try:
            web3 = await self.get_web3_with_proxy(address, use_proxy)
            router = web3.to_checksum_address(self.CASH_CONTRACT_ADDRESS)
            asset = web3.to_checksum_address(self.USDT_CONTRACT_ADDRESS)
            amount_wei = int(amount * 1e6)

            if not await self.approve_token(pk, address, router, asset, amount_wei, use_proxy):
                return False

            contract = web3.eth.contract(address=router, abi=self.CONTRACT_ABI)
            tx_data = contract.functions.subscribe(asset, amount_wei)  
            gas = tx_data.estimate_gas({"from": address})
            tx = tx_data.build_transaction({
                "from": address,
                "gas": int(gas * 1.3),
                "maxFeePerGas": web3.to_wei(2, "gwei"),
                "maxPriorityFeePerGas": web3.to_wei(1, "gwei"),
                "nonce": self.used_nonce[address],
                "chainId": web3.eth.chain_id,
            })
            signed = web3.eth.account.sign_transaction(tx, pk)
            tx_hash = await self.send_raw_tx(signed.raw_transaction.hex(), use_proxy, address)
            receipt = await self.wait_for_receipt(tx_hash, use_proxy, address)

            if receipt.status == 1:
                self.used_nonce[address] += 1
                self.subscribed_amounts.setdefault(address, []).append(amount)
                self.log(f"{Fore.GREEN+Style.BRIGHT}   Subscribe Success | {amount} USDT → CASH+{Style.RESET_ALL}")
                self.log(f"{Fore.CYAN+Style.BRIGHT}   Tx: {self.EXPLORER}{tx_hash}{Style.RESET_ALL}")
                return True
        except Exception as e:
            self.log(f"{Fore.RED+Style.BRIGHT}   Subscribe Failed: {str(e)[:80]}{Style.RESET_ALL}")
        return False

    async def perform_redemption(self, pk: str, address: str, amount: float, use_proxy: bool):
        try:
            web3 = await self.get_web3_with_proxy(address, use_proxy)
            router = web3.to_checksum_address(self.CASH_CONTRACT_ADDRESS)
            asset = web3.to_checksum_address(self.USDT_CONTRACT_ADDRESS)
            amount_wei = int(amount * 1e18)

            
            balance = await self.get_token_balance(address, self.CASH_CONTRACT_ADDRESS, use_proxy, is_usdt=False)
            if not balance or balance < amount:
                self.log(f"{Fore.YELLOW+Style.BRIGHT}   Insufficient CASH+ ({balance or 0:.6f} < {amount:.6f}){Style.RESET_ALL}")
                return False

            
            if not await self.approve_token(pk, address, router, self.CASH_CONTRACT_ADDRESS, amount_wei, use_proxy):
                return False

            contract = web3.eth.contract(address=router, abi=self.CONTRACT_ABI)
            tx_data = contract.functions.redemption(asset, amount_wei)  
            gas = tx_data.estimate_gas({"from": address})
            tx = tx_data.build_transaction({
                "from": address,
                "gas": int(gas * 1.3),
                "maxFeePerGas": web3.to_wei(2, "gwei"),
                "maxPriorityFeePerGas": web3.to_wei(1, "gwei"),
                "nonce": self.used_nonce[address],
                "chainId": web3.eth.chain_id,
            })
            signed = web3.eth.account.sign_transaction(tx, pk)
            tx_hash = await self.send_raw_tx(signed.raw_transaction.hex(), use_proxy, address)
            receipt = await self.wait_for_receipt(tx_hash, use_proxy, address)

            if receipt.status == 1:
                self.used_nonce[address] += 1
                if address in self.subscribed_amounts and amount in self.subscribed_amounts[address]:
                    self.subscribed_amounts[address].remove(amount)
                self.log(f"{Fore.GREEN+Style.BRIGHT}   Redeem Success | {amount:.6f} CASH+ → USDT{Style.RESET_ALL}")
                self.log(f"{Fore.CYAN+Style.BRIGHT}   Tx: {self.EXPLORER}{tx_hash}{Style.RESET_ALL}")
                return True
        except Exception as e:
            self.log(f"{Fore.RED+Style.BRIGHT}   Redeem Failed: {str(e)[:80]}{Style.RESET_ALL}")
        return False

    async def show_and_redeem_initial_cash(self, pk: str, address: str, use_proxy: bool):
        usdt_bal = await self.get_token_balance(address, self.USDT_CONTRACT_ADDRESS, use_proxy, is_usdt=True)
        cash_bal = await self.get_token_balance(address, self.CASH_CONTRACT_ADDRESS, use_proxy, is_usdt=False)

        self.log(f"{Fore.CYAN+Style.BRIGHT}   USDT Balance: {usdt_bal if usdt_bal is not None else 'Error'}{Style.RESET_ALL}")
        self.log(f"{Fore.MAGENTA+Style.BRIGHT}   CASH+ Balance: {cash_bal if cash_bal is not None else 'Error'}{Style.RESET_ALL}")

        if not cash_bal or cash_bal < 1:
            self.log(f"{Fore.YELLOW+Style.BRIGHT}   No CASH+ to redeem (balance: {cash_bal or 0:.6f}){Style.RESET_ALL}")
            return

        self.log(f"{Fore.MAGENTA+Style.BRIGHT}   [INITIAL] Redeeming ALL CASH+ → {cash_bal:.6f} USDT{Style.RESET_ALL}")
        success = await self.perform_redemption(pk, address, cash_bal, use_proxy)
        if success:
            self.log(f"{Fore.GREEN+Style.BRIGHT}   All CASH+ redeemed!{Style.RESET_ALL}")
        else:
            self.log(f"{Fore.RED+Style.BRIGHT}   Failed to redeem all CASH+{Style.RESET_ALL}")

    async def print_timer(self):
        delay = random.randint(self.min_delay, self.max_delay)
        for i in range(delay, 0, -1):
            print(f"{Fore.BLUE+Style.BRIGHT}Wait {i}s...{Style.RESET_ALL}", end="\r", flush=True)
            await asyncio.sleep(1)
        print(" " * 30, end="\r")

    def print_question(self):
        self.clear_terminal()
        self.welcome()

        while True:
            try:
                self.tx_count = int(input(f"{Fore.YELLOW + Style.BRIGHT}Tx Count (Cycles) -> {Style.RESET_ALL}"))
                if self.tx_count > 0: break
            except: pass

        while True:
            try:
                self.min_delay = int(input(f"{Fore.YELLOW + Style.BRIGHT}Min Delay (sec) -> {Style.RESET_ALL}"))
                if self.min_delay >= 0: break
            except: pass

        while True:
            try:
                self.max_delay = int(input(f"{Fore.YELLOW + Style.BRIGHT}Max Delay (sec) -> {Style.RESET_ALL}"))
                if self.max_delay >= self.min_delay: break
            except: pass

        while True:
            try:
                choice = int(input(f"{Fore.BLUE + Style.BRIGHT}1. With Proxy | 2. No Proxy -> {Style.RESET_ALL}"))
                if choice in [1, 2]:
                    return choice == 1
            except: pass

    async def process_account(self, pk: str, addr: str, use_proxy: bool):
        try:
            web3 = await self.get_web3_with_proxy(addr, use_proxy)
            self.used_nonce[addr] = web3.eth.get_transaction_count(addr, "pending")
            self.subscribed_amounts[addr] = []
        except Exception as e:
            self.log(f"{Fore.RED+Style.BRIGHT}Web3 Init Failed: {e}{Style.RESET_ALL}")
            return

        
        await self.show_and_redeem_initial_cash(pk, addr, use_proxy)
        await self.print_timer()

        
        for cycle in range(self.tx_count):
            self.log(f"{Fore.GREEN+Style.BRIGHT}Cycle {cycle+1}/{self.tx_count}{Style.RESET_ALL}")

            amount = random.randint(1, 5)
            self.log(f"{Fore.CYAN+Style.BRIGHT}   Subscribe {amount} USDT{Style.RESET_ALL}")

            usdt_balance = await self.get_token_balance(addr, self.USDT_CONTRACT_ADDRESS, use_proxy, is_usdt=True)
            if not usdt_balance or usdt_balance < amount:
                self.log(f"{Fore.YELLOW+Style.BRIGHT}   Insufficient USDT{Style.RESET_ALL}")
                break

            if not await self.perform_subscribe(pk, addr, amount, use_proxy):
                await self.print_timer()
                continue
            await self.print_timer()

            if addr in self.subscribed_amounts and self.subscribed_amounts[addr]:
                redeem_amt = self.subscribed_amounts[addr][-1]
                self.log(f"{Fore.CYAN+Style.BRIGHT}   Redeem {redeem_amt} CASH+{Style.RESET_ALL}")
                cash_balance = await self.get_token_balance(addr, self.CASH_CONTRACT_ADDRESS, use_proxy, is_usdt=False)
                if cash_balance and cash_balance >= redeem_amt:
                    await self.perform_redemption(pk, addr, redeem_amt, use_proxy)
                else:
                    self.log(f"{Fore.YELLOW+Style.BRIGHT}   Insufficient CASH+{Style.RESET_ALL}")
            await self.print_timer()

    async def main(self):
        try:
            with open('accounts.txt', 'r', encoding='utf-8') as f:
                accounts = [line.strip() for line in f if line.strip()]

            use_proxy = self.print_question()
            if use_proxy:
                await self.load_proxies()

            self.clear_terminal()
            self.welcome()
            self.log(f"{Fore.GREEN+Style.BRIGHT}Accounts: {len(accounts)}{Style.RESET_ALL}")

            for pk in accounts:
                addr = self.generate_address(pk)
                if not addr:
                    self.log(f"{Fore.RED+Style.BRIGHT}Invalid Private Key{Style.RESET_ALL}")
                    continue

                self.log(f"{Fore.CYAN+Style.BRIGHT}==[ {self.mask_account(addr)} ]=={Style.RESET_ALL}")
                await self.process_account(pk, addr, use_proxy)
                await asyncio.sleep(2)

            self.log(f"{Fore.CYAN+Style.BRIGHT}All Done. Restart in 24h...{Style.RESET_ALL}")
            await asyncio.sleep(24 * 3600)

        except FileNotFoundError:
            self.log(f"{Fore.RED+Style.BRIGHT}accounts.txt not found!{Style.RESET_ALL}")
        except KeyboardInterrupt:
            self.log(f"{Fore.RED+Style.BRIGHT}STOPPED BY USER{Style.RESET_ASSLET}")


if __name__ == "__main__":
    bot = AssetoFinance()
    asyncio.run(bot.main())
