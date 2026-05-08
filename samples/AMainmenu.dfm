object frmMain: TfrmMain
  Left = 223
  Top = 228
  Width = 387
  Height = 272
  Color = clBtnFace
  Font.Charset = DEFAULT_CHARSET
  Font.Color = clWindowText
  Font.Height = -11
  Font.Name = 'MS Sans Serif'
  Font.Style = []
  Menu = mmMain
  OldCreateOrder = False
  PixelsPerInch = 96
  TextHeight = 13

  object alMain: TActionList
    Left = 136
    Top = 96
    object acExit: TAction
      Caption = 'Exit'
      OnExecute = acExitExecute
    end
  end

  object ilMain: TImageList
    Left = 168
    Top = 96
  end

  object mmMain: TMainMenu
    Images = ilMain              { TImageList dihubungkan ke menu }
    Left = 40
    Top = 16
    object mmiFile: TMenuItem
      Caption = '&File'
      object miExit: TMenuItem
        Action = acExit
      end
    end
  end
end