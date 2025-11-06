"""Main CLI entry point for affinetes"""

import sys
import argparse
import asyncio
import json
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from ..utils.logger import logger
from .commands import (
    run_environment,
    list_environments,
    call_method,
    inspect_environment,
    stop_environment,
    show_logs
)

load_dotenv(override=True)

def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for CLI"""
    
    parser = argparse.ArgumentParser(
        prog='afs',
        description='Affinetes CLI - Container-based Environment Management',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start environment from image
  afs run bignickeye/affine:v2 --env CHUTES_API_KEY=xxx
  
  # Start from directory (auto build)
  afs run --dir environments/affine --tag affine:v2 --env CHUTES_API_KEY=xxx
  
  # List running environments
  afs list
  
  # Call method
  afs call affine-v2 evaluate --arg task_type=abd --arg num_samples=2
  
  # Inspect environment
  afs inspect affine-v2
  
  # Stop environment
  afs stop affine-v2
  
  # View logs
  afs logs affine-v2 --tail 50
"""
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # === run command ===
    run_parser = subparsers.add_parser(
        'run',
        help='Start an environment container'
    )
    run_parser.add_argument(
        'image',
        nargs='?',
        help='Docker image name (e.g., bignickeye/affine:v2)'
    )
    run_parser.add_argument(
        '--dir',
        dest='env_dir',
        help='Build from environment directory'
    )
    run_parser.add_argument(
        '--tag',
        help='Image tag when building from directory (default: auto-generated)'
    )
    run_parser.add_argument(
        '--name',
        help='Container name (default: derived from image)'
    )
    run_parser.add_argument(
        '--env',
        action='append',
        dest='env_vars',
        help='Environment variable (format: KEY=VALUE, can be specified multiple times)'
    )
    run_parser.add_argument(
        '--pull',
        action='store_true',
        help='Pull image before starting'
    )
    run_parser.add_argument(
        '--mem-limit',
        help='Memory limit (e.g., 512m, 1g, 2g)'
    )
    run_parser.add_argument(
        '--no-cache',
        action='store_true',
        help='Do not use cache when building (only with --dir)'
    )
    
    # === list command ===
    list_parser = subparsers.add_parser(
        'list',
        help='List running environments'
    )
    list_parser.add_argument(
        '--all',
        action='store_true',
        help='Show all containers including stopped ones'
    )
    list_parser.add_argument(
        '--json',
        action='store_true',
        help='Output in JSON format'
    )
    
    # === call command ===
    call_parser = subparsers.add_parser(
        'call',
        help='Call a method on running environment'
    )
    call_parser.add_argument(
        'name',
        help='Environment/container name'
    )
    call_parser.add_argument(
        'method',
        help='Method name to call'
    )
    call_parser.add_argument(
        '--arg',
        action='append',
        dest='args',
        help='Method argument (format: KEY=VALUE, can be specified multiple times)'
    )
    call_parser.add_argument(
        '--json',
        dest='json_args',
        help='JSON string for complex arguments'
    )
    call_parser.add_argument(
        '--timeout',
        type=int,
        help='Timeout in seconds'
    )
    
    # === inspect command ===
    inspect_parser = subparsers.add_parser(
        'inspect',
        help='Show environment details and available methods'
    )
    inspect_parser.add_argument(
        'name',
        help='Environment/container name'
    )
    
    # === stop command ===
    stop_parser = subparsers.add_parser(
        'stop',
        help='Stop running environment(s)'
    )
    stop_parser.add_argument(
        'names',
        nargs='+',
        help='Environment/container name(s)'
    )
    
    # === logs command ===
    logs_parser = subparsers.add_parser(
        'logs',
        help='View container logs'
    )
    logs_parser.add_argument(
        'name',
        help='Environment/container name'
    )
    logs_parser.add_argument(
        '--tail',
        type=int,
        default=100,
        help='Number of lines to show (default: 100)'
    )
    logs_parser.add_argument(
        '--follow',
        '-f',
        action='store_true',
        help='Follow log output'
    )
    
    return parser


def parse_env_vars(env_list: Optional[list]) -> Dict[str, str]:
    """Parse environment variables from KEY=VALUE format"""
    env_vars = {}
    if env_list:
        for env_str in env_list:
            if '=' not in env_str:
                logger.warning(f"Invalid env var format (should be KEY=VALUE): {env_str}")
                continue
            key, value = env_str.split('=', 1)
            env_vars[key] = value
    return env_vars


def parse_method_args(args_list: Optional[list], json_str: Optional[str]) -> Dict[str, Any]:
    """Parse method arguments from --arg and --json"""
    method_args = {}
    
    # Parse --arg KEY=VALUE
    if args_list:
        for arg_str in args_list:
            if '=' not in arg_str:
                logger.warning(f"Invalid arg format (should be KEY=VALUE): {arg_str}")
                continue
            key, value = arg_str.split('=', 1)
            
            # Try to parse as JSON value for complex types
            try:
                method_args[key] = json.loads(value)
            except json.JSONDecodeError:
                # Keep as string if not valid JSON
                method_args[key] = value
    
    # Parse --json (overrides --arg)
    if json_str:
        try:
            json_args = json.loads(json_str)
            method_args.update(json_args)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            sys.exit(1)
    
    return method_args


def main():
    """Main CLI entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    try:
        # Route to command handlers
        if args.command == 'run':
            # Validate run arguments
            if not args.image and not args.env_dir:
                parser.error("Either IMAGE or --dir must be specified")
            
            env_vars = parse_env_vars(args.env_vars)
            
            asyncio.run(run_environment(
                image=args.image,
                env_dir=args.env_dir,
                tag=args.tag,
                name=args.name,
                env_vars=env_vars,
                pull=args.pull,
                mem_limit=args.mem_limit,
                no_cache=args.no_cache
            ))
        
        elif args.command == 'list':
            asyncio.run(list_environments(
                show_all=args.all,
                json_output=args.json
            ))
        
        elif args.command == 'call':
            method_args = parse_method_args(args.args, args.json_args)
            
            asyncio.run(call_method(
                name=args.name,
                method=args.method,
                args=method_args,
                timeout=args.timeout
            ))
        
        elif args.command == 'inspect':
            asyncio.run(inspect_environment(name=args.name))
        
        elif args.command == 'stop':
            asyncio.run(stop_environment(names=args.names))
        
        elif args.command == 'logs':
            asyncio.run(show_logs(
                name=args.name,
                tail=args.tail,
                follow=args.follow
            ))
        
        else:
            parser.print_help()
            sys.exit(1)
    
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()