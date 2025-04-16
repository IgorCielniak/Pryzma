def register_commands(subparsers_action):
    """Add a greet command with arguments"""
    greet_parser = subparsers_action.add_parser(
        "greet",
        help="Greet someone with options"
    )
    
    # Required positional argument
    greet_parser.add_argument(
        "name",
        help="Person to greet"
    )
    
    # Optional arguments
    greet_parser.add_argument(
        "--formal",
        action="store_true",
        help="Use formal greeting"
    )
    
    greet_parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Number of times to repeat"
    )
    
    greet_parser.add_argument(
        "--volume",
        choices=["quiet", "normal", "loud"],
        default="normal",
        help="Volume level"
    )
    
    # Set the command function
    greet_parser.set_defaults(func=greet_command)

def greet_command(args):
    """Execute the greet command"""
    greeting = f"Good day to you, {args.name}" if args.formal else f"Hi {args.name}"
    
    if args.volume == "quiet":
        greeting = greeting.lower()
    elif args.volume == "loud":
        greeting = greeting.upper() + "!!!"
    
    for _ in range(args.repeat):
        print(greeting)
