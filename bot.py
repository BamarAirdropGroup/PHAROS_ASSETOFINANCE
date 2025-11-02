from web3 import Web3
from web3.exceptions import TransactionNotFound
from eth_account import Account
from aiohttp import ClientSession, ClientTimeout
from datetime import datetime
from colorama import *
import asyncio, random, re, os, pytz

wib = pytz.timezone('Asia/Singapore')

class AssetoFinance:
    def __init__(self) -> None:
        self.RPC_URL = "https://atlantic.dplabs-internal.com/"
        self.EXPLORER = "https://atlantic.pharosscan.xyz/tx/"
        self.USDT_CONTRACT_ADDRESS = "0xE7E84B8B4f39C507499c40B4ac199B050e2882d5"
        self.CASH_CONTRACT_ADDRESS = "0x56f4add11d723412D27A9e9433315401B351d6E3"
        self.CONTRACT_ABI = [
            {"inputs": [{"internalType": "address", "name": "owner", "type": "address"}, {"internalType": "address", "name": "spender", "type": "address"}], "name": "allowance", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "address", "name": "spender", "type": "address"}, {"internalType": "uint256", "name": "value", "type": "uint256"}], "name": "approve", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"internalType": "address", "name": "account", "type": "address"}], "name": "balanceOf", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "decimals", "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "address", "name": "uAddress", "type": "address"}, {"internalType": "uint256", "name": "tokenAmount", "type": "uint256"}], "name": "redemption", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"internalType": "address", "name": "uAddress", "type": "address"}, {"internalType": "uint256", "name": "uAmount", "type": "uint256"}], "name": "subscribe", "outputs": [], "stateMutability": "nonpayable", "type": "function"}
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
        print(f"{Fore.CYAN + Style.BRIGHT}[ {datetime.now().astimezone(wib).strftime('%x %X %Z')} ]{Style.RESET_ALL} {Fore.WHITE + Style.BRIGHT}|{Style.RESET_ALL} {message}", flush=True)

    def welcome(self):
        print(f"""
{Fore.GREEN + Style.BRIGHT} ╔═══════════════════════════════════════════════════╗
{Fore.GREEN + Style.BRIGHT} ║ Asseto Finance Auto BOT v5 ║
{Fore.GREEN + Style.BRIGHT} ║ Subscribe <---> Redeem  ║
{Fore.GREEN + Style.BRIGHT} ║ ║
{Fore.GREEN + Style.BRIGHT} ╚═══════════════════════════════════════════════════╝{Style.RESET_ALL}
        """)

    async def load_proxies(self):
        if not os.path.exists("proxy.txt"):
            self.log(f"{Fore.YELLOW + Style.BRIGHT}proxy.txt not found. Running without proxy.{Style.RESET_ALL}")
            return
        with open("proxy.txt", 'r') as f:
            self.proxies = [line.strip() for line in f if line.strip()]
        self.log(f"{Fore.GREEN + Style.BRIGHT}Loaded {len(self.proxies)} proxies (for balance check only){Style.RESET_ALL}")

    def get_next_proxy_for_account(self, addr):
        if addr not in self.account_proxies:
            if not self.proxies: return None
            proxy = self.proxies[self.proxy_index]
            self.account_proxies[addr] = proxy
            self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
        return self.account_proxies[addr]

    def generate_address(self, pk: str):
        try:
            return Account.from_key(pk).address
        except:
            return None

    def mask_account(self, addr):
        return addr[:6] + "******" + addr[-4:]

    async def get_web3(self):
        web3 = Web3(Web3.HTTPProvider(self.RPC_URL, request_kwargs={"timeout": 60}))
        try:
            web3.eth.get_block_number()
            return web3
        except:
            raise Exception("RPC Unreachable")

    async def get_token_balance(self, address: str, contract_addr: str, use_proxy: bool):
        try:
            web3 = await self.get_web3()
            contract = web3.eth.contract(address=web3.to_checksum_address(contract_addr), abi=self.CONTRACT_ABI)
            balance = contract.functions.balanceOf(address).call()
            decimals = contract.functions.decimals().call()
            return balance / (10 ** decimals)
        except Exception as e:
            self.log(f"{Fore.RED+Style.BRIGHT}Balance Error: {str(e)[:80]}{Style.RESET_ALL}")
            return None

    async def send_raw_transaction(self, signed_tx_hex: str):
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_sendRawTransaction",
            "params": [signed_tx_hex],
            "id": 1
        }
        async with ClientSession(timeout=ClientTimeout(total=30)) as session:
            async with session.post(self.RPC_URL, json=payload) as resp:
                data = await resp.json()
                if 'result' in data:
                    return data['result']
                elif 'error' in data:
                    err = data['error']
                    code = err.get('code', 0)
                    msg = err.get('message', '')
                    if code == -32600:
                        raise Exception("invalid_request")
                    raise Exception(f"RPC {code}: {msg}")
                raise Exception("Unknown RPC response")

    async def wait_for_receipt(self, web3, tx_hash, timeout=300):
        for _ in range(timeout // 3):
            try:
                receipt = web3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    return receipt
            except:
                pass
            await asyncio.sleep(3)
        raise Exception("Receipt timeout")

    async def approving_token(self, account: str, address: str, router: str, asset: str, amount_wei: int):
        web3 = await self.get_web3()
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
            signed = web3.eth.account.sign_transaction(tx, account)
            tx_hash = await self.send_raw_transaction(signed.raw_transaction.hex())
            receipt = await self.wait_for_receipt(web3, tx_hash)
            if receipt.status == 1:
                self.used_nonce[address] += 1
                self.log(f"{Fore.CYAN+Style.BRIGHT} Approve Success | Block: {receipt.blockNumber}{Style.RESET_ALL}")
                await asyncio.sleep(5)
                return True
        except Exception as e:
            self.log(f"{Fore.RED+Style.BRIGHT} Approve Failed: {str(e)[:80]}{Style.RESET_ALL}")
        return False

    async def perform_subscribe(self, account: str, address: str, amount: float, max_retries=3):
        for attempt in range(1, max_retries + 1):
            try:
                self.log(f"{Fore.CYAN+Style.BRIGHT} [Attempt {attempt}] Subscribe {amount} USDT{Style.RESET_ALL}")
                web3 = await self.get_web3()
                router = web3.to_checksum_address(self.CASH_CONTRACT_ADDRESS)
                asset = web3.to_checksum_address(self.USDT_CONTRACT_ADDRESS)
                amount_wei = int(amount * 1e6)
                if not await self.approving_token(account, address, router, asset, amount_wei):
                    continue
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
                signed = web3.eth.account.sign_transaction(tx, account)
                tx_hash = await self.send_raw_transaction(signed.raw_transaction.hex())
                receipt = await self.wait_for_receipt(web3, tx_hash)
                if receipt.status == 1:
                    self.used_nonce[address] += 1
                    self.subscribed_amounts.setdefault(address, []).append(amount)
                    self.log(f"{Fore.GREEN+Style.BRIGHT} Success | Block: {receipt.blockNumber}{Style.RESET_ALL}")
                    self.log(f"{Fore.CYAN+Style.BRIGHT} Tx: {self.EXPLORER}{tx_hash}{Style.RESET_ALL}")
                    return True
                else:
                    raise Exception("TX reverted")
            except Exception as e:
                err = str(e).lower()
                self.log(f"{Fore.YELLOW+Style.BRIGHT} [Attempt {attempt}] Failed: {err[:100]}{Style.RESET_ALL}")
                if "nonce" in err or "already known" in err or "invalid_request" in err:
                    self.used_nonce[address] = web3.eth.get_transaction_count(address, "pending")
                if attempt < max_retries:
                    await asyncio.sleep(3 * attempt)
                else:
                    self.log(f"{Fore.RED+Style.BRIGHT} Subscribe Failed Permanently{Style.RESET_ALL}")
                    return False
        return False

    async def perform_redemption(self, account: str, address: str, amount: float, max_retries=3):
        for attempt in range(1, max_retries + 1):
            try:
                self.log(f"{Fore.CYAN+Style.BRIGHT} [Attempt {attempt}] Redeem {amount} CASH+{Style.RESET_ALL}")
                web3 = await self.get_web3()
                router = web3.to_checksum_address(self.CASH_CONTRACT_ADDRESS)
                asset = web3.to_checksum_address(self.USDT_CONTRACT_ADDRESS)
                amount_wei = int(amount * 1e18)
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
                signed = web3.eth.account.sign_transaction(tx, account)
                tx_hash = await self.send_raw_transaction(signed.raw_transaction.hex())
                receipt = await self.wait_for_receipt(web3, tx_hash)
                if receipt.status == 1:
                    self.used_nonce[address] += 1
                    if address in self.subscribed_amounts and amount in self.subscribed_amounts[address]:
                        self.subscribed_amounts[address].remove(amount)
                    self.log(f"{Fore.GREEN+Style.BRIGHT} Success | Block: {receipt.blockNumber}{Style.RESET_ALL}")
                    self.log(f"{Fore.CYAN+Style.BRIGHT} Tx: {self.EXPLORER}{tx_hash}{Style.RESET_ALL}")
                    return True
                else:
                    raise Exception("TX reverted")
            except Exception as e:
                err = str(e).lower()
                self.log(f"{Fore.YELLOW+Style.BRIGHT} [Attempt {attempt}] Failed: {err[:100]}{Style.RESET_ALL}")
                if "nonce" in err or "invalid_request" in err:
                    self.used_nonce[address] = web3.eth.get_transaction_count(address, "pending")
                if attempt < max_retries:
                    await asyncio.sleep(3 * attempt)
                else:
                    self.log(f"{Fore.RED+Style.BRIGHT} Redeem Failed Permanently{Style.RESET_ALL}")
                    return False
        return False

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
                use_proxy = int(input(f"{Fore.BLUE + Style.BRIGHT}1. With Proxy | 2. No Proxy -> {Style.RESET_ALL}"))
                if use_proxy in [1, 2]: break
            except: pass
        return use_proxy == 1

    async def process_account(self, pk: str, addr: str, use_proxy: bool):
        try:
            web3 = await self.get_web3()
            self.used_nonce[addr] = web3.eth.get_transaction_count(addr, "pending")
            self.subscribed_amounts[addr] = []
        except Exception as e:
            self.log(f"{Fore.RED+Style.BRIGHT}Web3 Init Failed: {e}{Style.RESET_ALL}")
            return

        for cycle in range(self.tx_count):
            self.log(f"{Fore.GREEN+Style.BRIGHT}Cycle {cycle+1}/{self.tx_count}{Style.RESET_ALL}")

            # === GET CURRENT USDT BALANCE ===
            balance = await self.get_token_balance(addr, self.USDT_CONTRACT_ADDRESS, use_proxy)
            if not balance or balance < 1:
                self.log(f"{Fore.YELLOW+Style.BRIGHT}Insufficient USDT (balance: {balance or 0:.2f} USDT){Style.RESET_ALL}")
                break

            # === DYNAMIC RANDOM AMOUNT: 1 to floor(balance) ===
            max_amount = int(balance)  # e.g. 6.73 → 6
            amount = random.randint(1, max_amount)

            self.log(f"{Fore.CYAN+Style.BRIGHT}Subscribe {amount} USDT (Balance: {balance:.2f} USDT){Style.RESET_ALL}")

            if not await self.perform_subscribe(pk, addr, amount):
                self.log(f"{Fore.RED+Style.BRIGHT}Subscribe Failed. Skip Cycle.{Style.RESET_ALL}")
                await self.print_timer()
                continue

            await self.print_timer()

            # === REDEEM LAST SUBSCRIBED AMOUNT ===
            if addr in self.subscribed_amounts and self.subscribed_amounts[addr]:
                redeem_amt = self.subscribed_amounts[addr][-1]
                self.log(f"{Fore.CYAN+Style.BRIGHT}Redeem {redeem_amt} CASH+{Style.RESET_ALL}")
                cash_balance = await self.get_token_balance(addr, self.CASH_CONTRACT_ADDRESS, use_proxy)
                if cash_balance and cash_balance >= redeem_amt:
                    await self.perform_redemption(pk, addr, redeem_amt)
                else:
                    self.log(f"{Fore.YELLOW+Style.BRIGHT}Insufficient CASH+ (have {cash_balance or 0:.2f}){Style.RESET_ALL}")
            await self.print_timer()

    async def main(self):
        try:
            with open('accounts.txt', 'r') as f:
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
            self.log(f"{Fore.RED+Style.BRIGHT}STOPPED BY USER{Style.RESET_ALL}")

if __name__ == "__main__":
    bot = AssetoFinance()
    asyncio.run(bot.main())
