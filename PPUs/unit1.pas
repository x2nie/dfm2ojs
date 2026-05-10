unit Unit1;

{$mode objfpc}{$H+}{$M+}

interface

uses
  Classes, SysUtils;

type
  TFooMode = (fmSmall, fmMedium, fmLarge);
  TFooOptions = set of TFooMode;

  TFoo = class(TPersistent)
  private
    FCount: Integer;
    FEnabled: Boolean;
    FMode: TFooMode;
    FName: string;
    FOptions: TFooOptions;
  published
    property Count: Integer read FCount write FCount default 7;
    property Enabled: Boolean read FEnabled write FEnabled default True;
    property Mode: TFooMode read FMode write FMode default fmMedium;
    property Name: string read FName write FName;
    property Options: TFooOptions read FOptions write FOptions;
  end;

  TBar = class(TFoo)
  private
    FLevel: Integer;
    FTitle: string;
    FVisible: Boolean;
  published
    property Level: Integer read FLevel write FLevel default 3;
    property Title: string read FTitle write FTitle;
    property Visible: Boolean read FVisible write FVisible default False;
  end;

implementation

end.
